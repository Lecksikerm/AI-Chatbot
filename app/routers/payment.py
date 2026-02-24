from fastapi import APIRouter, Depends, HTTPException, Request, Header
from paystackapi.paystack import Paystack
from paystackapi.transaction import Transaction
from datetime import datetime, timedelta
import os
import hmac
import hashlib
import json

from app.auth import get_current_active_user
from app.db import db

router = APIRouter(prefix="/payments", tags=["payments"])

paystack = Paystack(secret_key=os.getenv("PAYSTACK_SECRET_KEY"))

PLANS = {
    "pro_monthly": {"name": "Pro Monthly", "price": 500000, "message_limit": 1000, "interval": "monthly"},  # ₦5,000
    "pro_yearly": {"name": "Pro Yearly", "price": 5000000, "message_limit": 10000, "interval": "yearly"},  # ₦50,000
}

@router.get("/plans")
async def get_plans():
    """Get available subscription plans"""
    return {"plans": PLANS}

@router.post("/initialize")
async def initialize_payment(plan: str, current_user: dict = Depends(get_current_active_user)):
    """Initialize Paystack payment"""
    if plan not in PLANS:
        raise HTTPException(status_code=400, detail="Invalid plan")
    
    # Check if user already has pending payment
    existing = db.payments.find_one({
        "user_id": current_user["id"],
        "status": "pending",
        "plan": plan
    })
    
    if existing:
        # Return existing payment link
        return {
            "authorization_url": existing["authorization_url"],
            "reference": existing["reference"]
        }
    
    plan_details = PLANS[plan]
    reference = f"{current_user['id']}_{plan}_{int(datetime.utcnow().timestamp())}"
    
    try:
        # Initialize transaction
        response = Transaction.initialize(
            reference=reference,
            amount=plan_details["price"],
            email=current_user["email"],
            callback_url=f"{os.getenv('FRONTEND_URL')}/payment/verify"
        )
        
        if response["status"]:
            # Store pending payment
            db.payments.insert_one({
                "user_id": current_user["id"],
                "reference": reference,
                "plan": plan,
                "amount": plan_details["price"],
                "status": "pending",
                "authorization_url": response["data"]["authorization_url"],
                "created_at": datetime.utcnow()
            })
            
            return {
                "authorization_url": response["data"]["authorization_url"],
                "reference": reference
            }
        else:
            raise HTTPException(status_code=400, detail="Payment initialization failed")
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Payment error: {str(e)}")

@router.get("/verify/{reference}")
async def verify_payment(reference: str, current_user: dict = Depends(get_current_active_user)):
    """Manual verification (fallback if webhook fails)"""
    return await process_verification(reference)

@router.post("/webhook")
async def paystack_webhook(request: Request, x_paystack_signature: str = Header(None)):
    """Handle Paystack webhook for automatic verification"""
    
    # Get raw payload
    payload = await request.body()
    
    # Verify webhook signature
    secret = os.getenv("PAYSTACK_SECRET_KEY", "").encode()
    if not secret:
        raise HTTPException(status_code=500, detail="Webhook secret not configured")
    
    expected_sig = hmac.new(secret, payload, hashlib.sha512).hexdigest()
    
    if x_paystack_signature != expected_sig:
        raise HTTPException(status_code=400, detail="Invalid signature")
    
    # Parse webhook data
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")
    
    event = data.get("event")
    
    # Handle successful payment
    if event == "charge.success":
        reference = data["data"]["reference"]
        return await process_verification(reference)
    
    return {"status": "ignored", "event": event}

async def process_verification(reference: str):
    """Process payment verification (used by both webhook and manual endpoint)"""
    payment = db.payments.find_one({"reference": reference})
    
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    
    if payment["status"] == "success":
        return {"status": "success", "message": "Payment already verified"}
    
    # Verify with Paystack API
    try:
        response = Transaction.verify(reference=reference)
        
        if not response["status"] or response["data"]["status"] != "success":
            db.payments.update_one(
                {"reference": reference},
                {"$set": {"status": "failed", "updated_at": datetime.utcnow()}}
            )
            raise HTTPException(status_code=400, detail="Payment verification failed")
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Verification error: {str(e)}")
    
    # Update payment status
    db.payments.update_one(
        {"reference": reference},
        {"$set": {"status": "success", "paid_at": datetime.utcnow()}}
    )
    
    # Get plan details
    plan = PLANS.get(payment["plan"], {})
    interval_days = 365 if "yearly" in payment["plan"] else 30
    
    # Update user subscription
    db.users.update_one(
        {"id": payment["user_id"]},
        {"$set": {
            "role": "pro",
            "message_limit": plan.get("message_limit", 1000),
            "subscription_expires_at": datetime.utcnow() + timedelta(days=interval_days),
            "updated_at": datetime.utcnow()
        }}
    )
    
    return {"status": "success", "message": "Payment verified. You are now Pro!"}