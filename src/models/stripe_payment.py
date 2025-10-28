"""
Stripe payment catalog and subscription models for POLARIS.

Two-table catalog (PaymentPlan + PlanPrice) and team-scoped TeamSubscription
that mirrors Stripe subscription state. No migrations run yet.
"""
from datetime import datetime, UTC
import uuid

from src.extensions import db


class PaymentPlan(db.Model):
    """Catalog plan: features and limits (not tied to billing interval/amount)."""
    __tablename__ = 'payment_plans'

    # Primary key
    id = db.Column(db.Integer, primary_key=True)

    # Public UUID (non-primary)
    payment_plan_uuid = db.Column(db.String(36), unique=True, index=True, default=lambda: str(uuid.uuid4()))

    # Identity
    code = db.Column(db.String(50), unique=True, nullable=False, index=True)  # e.g., "basic", "pro"
    display_name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)

    # Stripe product
    stripe_product_id = db.Column(db.String(100), nullable=True, index=True)

    # Explicit limits
    max_teams = db.Column(db.Integer, nullable=False, default=0)  # 0 = not allowed
    # Use -1 for unlimited counts
    max_projects = db.Column(db.Integer, nullable=False, default=-1)
    max_team_members_per_team = db.Column(db.Integer, nullable=False, default=1)
    max_project_members_per_project = db.Column(db.Integer, nullable=False, default=-1)

    # Feature gates
    can_add_users_to_project = db.Column(db.Boolean, nullable=False, default=False)
    features = db.Column(db.JSON, nullable=True)

    # Lifecycle
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    sort_order = db.Column(db.Integer, nullable=False, default=100)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(UTC))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))
    deleted_at = db.Column(db.DateTime, nullable=True)
    is_deleted = db.Column(db.Boolean, nullable=False, default=False, index=True)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    deleted_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    # Relationships
    creator = db.relationship('User', foreign_keys=[created_by], backref='created_payment_plans')
    deleter = db.relationship('User', foreign_keys=[deleted_by], backref='deleted_payment_plans')
    prices = db.relationship('PlanPrice', back_populates='plan', cascade='all, delete-orphan')

    __table_args__ = (
        db.CheckConstraint("max_teams >= 0", name="chk_pp_max_teams_nonneg"),
        db.CheckConstraint("max_projects >= -1", name="chk_pp_max_projects_gte_neg1"),
        db.CheckConstraint("max_team_members_per_team >= 0", name="chk_pp_max_team_members_nonneg"),
        db.CheckConstraint("max_project_members_per_project >= -1", name="chk_pp_max_project_members_gte_neg1"),
    )

    def __repr__(self):
        return f'<PaymentPlan {self.id}: {self.code}>'


class PlanPrice(db.Model):
    """Concrete sellable price per interval (e.g., monthly/yearly), with trial length."""
    __tablename__ = 'plan_prices'

    # Primary key
    id = db.Column(db.Integer, primary_key=True)

    # Public UUID (non-primary)
    plan_price_uuid = db.Column(db.String(36), unique=True, index=True, default=lambda: str(uuid.uuid4()))

    # FK to plan
    plan_id = db.Column(db.Integer, db.ForeignKey('payment_plans.id', ondelete='CASCADE'), nullable=False, index=True)

    # Identity
    key = db.Column(db.String(80), unique=True, nullable=False, index=True)  # e.g., "basic_monthly"
    nickname = db.Column(db.String(100), nullable=True)

    # Pricing
    currency = db.Column(db.String(10), nullable=False, default='usd')
    amount_cents = db.Column(db.Integer, nullable=False)
    compare_at_cents = db.Column(db.Integer, nullable=True)

    # Interval
    interval = db.Column(db.String(20), nullable=False)  # 'month' | 'year'
    interval_count = db.Column(db.Integer, nullable=False, default=1)

    # Trial (default displayed; Stripe mirrors in subscription)
    trial_days = db.Column(db.Integer, nullable=False, default=14)

    # Stripe linkage
    stripe_price_id = db.Column(db.String(100), nullable=True, unique=True, index=True)

    # Per-seat pricing (optional)
    per_seat_amount_cents = db.Column(db.Integer, nullable=True)  # e.g., 5000 BRL cents per extra member
    per_seat_metric = db.Column(db.String(50), nullable=True, default='team_member')

    # Lifecycle
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(UTC))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))

    # Relationship
    plan = db.relationship('PaymentPlan', back_populates='prices')

    __table_args__ = (
        db.CheckConstraint("amount_cents >= 0", name="chk_price_amount_nonneg"),
        db.CheckConstraint("compare_at_cents IS NULL OR compare_at_cents >= 0", name="chk_price_compare_at_nonneg"),
        db.CheckConstraint("interval IN ('month','year')", name="chk_price_interval"),
        db.CheckConstraint("interval_count >= 1", name="chk_price_interval_count"),
        db.CheckConstraint("trial_days >= 0", name="chk_price_trial_days_nonneg"),
        db.CheckConstraint("per_seat_amount_cents IS NULL OR per_seat_amount_cents >= 0", name="chk_price_per_seat_nonneg"),
    )

    def __repr__(self):
        return f'<PlanPrice {self.id}: {self.key}>'


class TeamSubscription(db.Model):
    """Live subscription for a team. Mirrors Stripe subscription state & dates."""
    __tablename__ = 'team_subscriptions'

    # Primary key
    id = db.Column(db.Integer, primary_key=True)

    # Public UUID (non-primary)
    team_subscription_uuid = db.Column(db.String(36), unique=True, index=True, default=lambda: str(uuid.uuid4()))

    # Ownership
    team_id = db.Column(db.Integer, db.ForeignKey('teams.id', ondelete='CASCADE'), nullable=False, index=True)
    billing_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)

    # Catalog linkage
    plan_id = db.Column(db.Integer, db.ForeignKey('payment_plans.id'), nullable=False)
    price_id = db.Column(db.Integer, db.ForeignKey('plan_prices.id'), nullable=False)

    # Status & quantity
    status = db.Column(db.String(30), nullable=False, default='trialing', index=True)  # trialing, active, past_due, canceled, incomplete, incomplete_expired
    quantity = db.Column(db.Integer, nullable=False, default=1)

    # Trial & period windows (UTC)
    trial_end = db.Column(db.DateTime, nullable=True, index=True)
    current_period_start = db.Column(db.DateTime, nullable=True)
    current_period_end = db.Column(db.DateTime, nullable=True)

    # Cancellation
    cancel_at_period_end = db.Column(db.Boolean, nullable=False, default=False)
    canceled_at = db.Column(db.DateTime, nullable=True)

    # Stripe ids
    stripe_customer_id = db.Column(db.String(100), nullable=True, index=True)
    stripe_subscription_id = db.Column(db.String(100), nullable=True, unique=True, index=True)
    stripe_latest_invoice_id = db.Column(db.String(100), nullable=True)

    # Promotions
    stripe_coupon_id = db.Column(db.String(100), nullable=True)
    stripe_promo_code_id = db.Column(db.String(100), nullable=True)
    discount_ends_at = db.Column(db.DateTime, nullable=True)

    # Fast-path flags and extra metadata
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    trial_consumed = db.Column(db.Boolean, nullable=False, default=False)
    extra_data = db.Column(db.JSON, nullable=True, default=dict)

    # Lifecycle
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(UTC))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))
    deleted_at = db.Column(db.DateTime, nullable=True)
    is_deleted = db.Column(db.Boolean, nullable=False, default=False, index=True)

    # Relationships
    plan = db.relationship('PaymentPlan')
    price = db.relationship('PlanPrice')
    team = db.relationship('Team', backref='subscriptions')
    billing_user = db.relationship('User', foreign_keys=[billing_user_id], backref='billed_subscriptions')

    __table_args__ = (
        db.CheckConstraint("quantity >= 1", name="chk_sub_quantity_pos"),
        db.Index('ix_team_subscription_active', 'team_id', 'status'),
    )

    def __repr__(self):
        return f'<TeamSubscription {self.id}: Team {self.team_id} {self.status}>'
