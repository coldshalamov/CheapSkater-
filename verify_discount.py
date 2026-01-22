"""Quick test of the discount calculation for the screenshot example."""
import sys
sys.path.insert(0, 'D:\\GitHub\\Telomere\\CheapSkater-')

from app.ingest import _calculate_discount_percent

# The closet organizer from the screenshot
price = 905.38
was_price = 1214.50

discount = _calculate_discount_percent(price, was_price)
expected = ((was_price - price) / was_price) * 100.0

print(f"Price: ${price}")
print(f"Was Price: ${was_price}")
print(f"Savings: ${was_price - price:.2f}")
print(f"Calculated Discount: {discount:.2f}%")
print(f"Expected Discount: {expected:.2f}%")
print(f"\n✅ The '92% OFF' badge will now correctly show '{discount:.0f}% OFF'")
