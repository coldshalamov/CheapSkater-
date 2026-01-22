"""Test discount percentage calculation fix."""
from app.ingest import _calculate_discount_percent


def test_discount_calculation():
    """Test that discount percentages are calculated correctly."""
    
    # Test case from the screenshot: $905.38 from $1,214.50
    # Should be ~25.5%, NOT 92%
    price = 905.38
    was_price = 1214.50
    actual_discount = _calculate_discount_percent(price, was_price)
    expected_discount = ((was_price - price) / was_price) * 100.0
    
    print(f"Price: ${price}")
    print(f"Was Price: ${was_price}")
    print(f"Calculated Discount: {actual_discount:.2f}%")
    print(f"Expected Discount: {expected_discount:.2f}%")
    
    assert abs(actual_discount - expected_discount) < 0.01, "Discount calculation mismatch"
    assert actual_discount < 30, f"Discount should be ~25%, not {actual_discount}%"
    assert actual_discount > 20, f"Discount should be ~25%, not {actual_discount}%"
    
    # Test edge cases
    assert _calculate_discount_percent(100, 200) == 50.0, "50% discount failed"
    assert _calculate_discount_percent(10, 100) == 90.0, "90% discount failed"
    assert _calculate_discount_percent(100, 100) == 0.0, "No discount failed"
    assert _calculate_discount_percent(150, 100) == 0.0, "Price increase should be 0%"
    assert _calculate_discount_percent(0, 100) == 0.0, "Zero price should be 0%"
    assert _calculate_discount_percent(100, 0) == 0.0, "Zero was_price should be 0%"
    
    print("\n✅ All discount calculation tests passed!")


if __name__ == "__main__":
    test_discount_calculation()
