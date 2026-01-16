from __future__ import annotations

from typing import List, Optional, Dict

from pydantic import BaseModel, Field


class ProductOut(BaseModel):
    product_id: int
    sku: str
    product_name: str
    category_l1: str
    category_l2: str
    brand: str
    list_price: float
    discount_pct: int
    sell_price: float
    image_url: str


class ProductDetailOut(ProductOut):
    description: str
    in_stock: bool = True
    stock_qty: int = 0


class CartItemIn(BaseModel):
    product_id: int
    qty: int = Field(ge=1, le=20)


class OrderAddressIn(BaseModel):
    recipient_name: str = Field(max_length=200)
    phone: str = Field(max_length=30)
    address_line1: str = Field(max_length=300)
    address_line2: str = Field(max_length=300, default="")
    city: str = Field(max_length=100)
    state: str = Field(max_length=100)
    postal_code: str = Field(max_length=20)
    country: str = Field(max_length=60)


class CustomerAddressOut(BaseModel):
    address_id: int
    label: Optional[str] = None
    recipient_name: str
    phone: str
    address_line1: str
    address_line2: str
    city: str
    state: str
    postal_code: str
    country: str
    is_default: bool


class CreateCustomerAddressIn(BaseModel):
    label: Optional[str] = Field(default=None, max_length=40)
    recipient_name: str = Field(max_length=200)
    phone: str = Field(max_length=30)
    address_line1: str = Field(max_length=300)
    address_line2: str = Field(max_length=300, default="")
    city: str = Field(max_length=100)
    state: str = Field(max_length=100)
    postal_code: str = Field(max_length=20)
    country: str = Field(max_length=60)
    is_default: bool = False


class UpdateCustomerAddressIn(BaseModel):
    label: Optional[str] = Field(default=None, max_length=40)
    recipient_name: str = Field(max_length=200)
    phone: str = Field(max_length=30)
    address_line1: str = Field(max_length=300)
    address_line2: str = Field(max_length=300, default="")
    city: str = Field(max_length=100)
    state: str = Field(max_length=100)
    postal_code: str = Field(max_length=20)
    country: str = Field(max_length=60)
    is_default: bool = False


class CreateOrderRequest(BaseModel):
    items: List[CartItemIn]
    channel: str = "WEB"
    currency: Optional[str] = None
    customer_id: Optional[int] = None
    promo_code: Optional[str] = Field(default=None, max_length=40)
    payment_method: str = "UPI"
    simulate_payment_failure: bool = False
    failure_reason: Optional[str] = Field(default=None, max_length=80)
    address: Optional[OrderAddressIn] = None


class OrderCreatedOut(BaseModel):
    order_id: int
    net_amount: float
    order_status: Optional[str] = None
    payment_status: Optional[str] = None
    promo_code: Optional[str] = None
    promo_discount_amount: Optional[float] = None


class FunnelEventIn(BaseModel):
    session_id: str = Field(min_length=6, max_length=64)
    stage: str
    channel: str = "WEB"
    device: str = "DESKTOP"
    customer_id: Optional[int] = None
    product_id: Optional[int] = None
    order_id: Optional[int] = None
    failure_reason: Optional[str] = Field(default=None, max_length=80)


class KpisLatestOut(BaseModel):
    snapshot_ts: str
    label: str
    metrics: Dict[str, float]


class AdminKpisLatestOut(KpisLatestOut):
    kpi_last_updated_at: str


class CustomerResolveIn(BaseModel):
    email: str


class CustomerResolveOut(BaseModel):
    email: str
    customer_id: int
    geo_id: int


class AuthRequestOtpIn(BaseModel):
    email: str


class AuthRequestOtpOut(BaseModel):
    email: str
    otp_sent: bool
    expires_in_seconds: int
    demo_otp: Optional[str] = None


class AuthEmailExistsOut(BaseModel):
    email: str
    exists: bool


class AuthVerifyOtpIn(BaseModel):
    email: str
    otp: str


class AuthVerifyOtpOut(BaseModel):
    email: str
    customer_id: int
    geo_id: int


class AuthSignupRequestOtpIn(BaseModel):
    email: str
    display_name: str
    password: str


class AuthSignupRequestOtpOut(BaseModel):
    email: str
    otp_sent: bool
    expires_in_seconds: int
    demo_otp: Optional[str] = None


class AuthSignupVerifyOtpIn(BaseModel):
    email: str
    otp: str


class AuthSignupVerifyOtpOut(BaseModel):
    email: str
    customer_id: int
    geo_id: int
    display_name: Optional[str] = None


class AuthLoginIn(BaseModel):
    email: str
    password: str


class AuthLoginOut(BaseModel):
    email: str
    customer_id: int
    geo_id: int
    display_name: Optional[str] = None


class AdminLoginIn(BaseModel):
    username: str
    password: str


class AdminLoginOut(BaseModel):
    admin_key: str


class AdminOrderSummaryOut(BaseModel):
    order_id: int
    customer_id: int
    customer_name: Optional[str] = None
    customer_email: Optional[str] = None
    order_ts: str
    order_status: str
    net_amount: float
    channel: Optional[str] = None


class JourneySessionOut(BaseModel):
    session_id: str
    customer_id: Optional[int] = None
    first_event_ts: str
    last_event_ts: str
    event_count: int
    channel: Optional[str] = None
    device: Optional[str] = None


class JourneyEventOut(BaseModel):
    event_id: int
    event_ts: str
    session_id: str
    customer_id: Optional[int] = None
    stage: str
    channel: Optional[str] = None
    device: Optional[str] = None
    product_id: Optional[int] = None
    order_id: Optional[int] = None
    failure_reason: Optional[str] = None


class OrderSummaryOut(BaseModel):
    order_id: int
    order_ts: str
    order_status: str
    net_amount: float


class OrderItemSummaryOut(BaseModel):
    product_id: int
    product_name: str
    qty: int


class OrderWithItemsOut(OrderSummaryOut):
    items: List[OrderItemSummaryOut] = Field(default_factory=list)


class OrdersByCustomerOut(BaseModel):
    customer_id: int
    orders: List[OrderWithItemsOut]


class PromoValidateOut(BaseModel):
    code: str
    valid: bool
    discount_amount: float
    message: Optional[str] = None


class WishlistItemOut(ProductOut):
    added_at: str


class ProductReviewIn(BaseModel):
    rating: int = Field(ge=1, le=5)
    title: Optional[str] = Field(default=None, max_length=120)
    body: Optional[str] = None


class ProductReviewOut(BaseModel):
    review_id: int
    product_id: int
    customer_id: int
    rating: int
    title: Optional[str] = None
    body: Optional[str] = None
    created_at: str
    updated_at: str


class ProductRatingSummaryOut(BaseModel):
    product_id: int
    average_rating: float
    rating_count: int


class CustomerEmailOut(BaseModel):
    email_id: int
    to_email: str
    subject: str
    body: str
    kind: str
    order_id: Optional[int] = None
    status: str
    created_at: str
    sent_at: Optional[str] = None


class OrderDetailOut(BaseModel):
    order_id: int
    customer_id: int
    order_ts: str
    order_status: str
    payment_status: Optional[str] = None
    net_amount: float
    gross_amount: float
    discount_amount: float
    tax_amount: float
    promo_code: Optional[str] = None
    promo_discount_amount: Optional[float] = None
    items: List[OrderItemSummaryOut] = Field(default_factory=list)


class CancelOrderIn(BaseModel):
    customer_id: int
    reason: Optional[str] = Field(default=None, min_length=1, max_length=300)


class CancelOrderOut(BaseModel):
    order_id: int
    order_status: str


class OrderTimelineStageOut(BaseModel):
    stage: str
    timestamp: Optional[str] = None


class OrderTimelineOut(BaseModel):
    order_id: int
    current_status: str
    stages: List[OrderTimelineStageOut]
    cancellation_reason: Optional[str] = None


class AdminAuditLogItemOut(BaseModel):
    event_ts: str
    order_id: int
    action: str
    reason: Optional[str] = None
    actor_type: str


class FinanceSummaryOut(BaseModel):
    orders: int
    revenue_ex_tax: float
    cogs: float
    gross_profit_ex_tax: float
    shipping_cost: float
    gateway_fee_amount: float
    refund_amount: float
    net_profit_ex_tax: float
    gross_margin_pct: float
    net_margin_pct: float
    loss_orders: int
    discount_heavy_orders: int
    return_orders: int
    sla_breached_orders: int


class FinanceOrderPnlOut(BaseModel):
    order_id: int
    customer_id: int
    order_ts: str
    order_status: str
    revenue_ex_tax: float
    cogs: float
    gross_profit_ex_tax: float
    shipping_cost: float
    gateway_fee_amount: float
    refund_amount: float
    net_profit_ex_tax: float
    discount_amount: float
    loss_order_flag: bool
    discount_heavy_flag: bool
    has_return_flag: bool
    sla_breached_flag: bool


class FinanceProductPnlOut(BaseModel):
    product_id: int
    product_name: str
    category_l1: str
    category_l2: str
    brand: str
    revenue_ex_tax: float
    net_profit_ex_tax: float
    net_margin_pct: float
    loss_product_flag: bool


class FinanceCustomerPnlOut(BaseModel):
    customer_id: int
    acquisition_channel: str
    region: str
    country: str
    orders: int
    revenue_ex_tax: float
    net_profit_ex_tax: float
    net_margin_pct: float
    loss_customer_flag: bool


class FunnelSummaryOut(BaseModel):
    window_days: int
    product_views: int
    add_to_cart: int
    checkout_started: int
    payment_attempts: int
    orders_placed: int
    conversion_rate: float
    cart_abandonment_rate: float
    payment_failure_rate: float
    net_revenue_ex_tax: float
    revenue_lost_cart_abandonment: float
    revenue_lost_payment_failures: float
    refunds_leakage: float
    net_revenue_after_leakage: float


class FunnelDailyMetricOut(BaseModel):
    event_dt: str
    product_views: int
    add_to_cart: int
    checkout_started: int
    payment_attempts: int
    orders_placed: int
    conversion_rate: float
    cart_abandonment_rate: float
    payment_failure_rate: float


class FunnelProductLeakageOut(BaseModel):
    product_id: int
    product_name: str
    product_views: int
    add_to_cart: int
    abandoned_adds: int
    revenue_lost_cart_abandonment: float
    failed_orders: int
    revenue_lost_payment_failures: float


class FunnelPaymentFailureOut(BaseModel):
    event_dt: str
    payment_method: str
    payment_provider: str
    failure_reason: Optional[str] = None
    failed_payments: int
    amount_attempted: float
    revenue_at_risk_ex_tax: float
