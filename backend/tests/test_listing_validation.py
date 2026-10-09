from app.domain.bilibili import ProductAddRequest


def request():
    return ProductAddRequest.model_validate({
        'category_leaf_id': 2301, 'name': '商品名称测试', 'pic': 'https://example.com/a.jpg',
        'freight_id': 1, 'delivery_delay_day': 3,
        'spec_info': {'spec_values': [{'property_name': '款式', 'values': [{'value_name': 'A'}, {'value_name': 'B'}]}]},
        'spec_prices': [{'stock_num': 1, 'price': 100, 'sell_properties': [{'property_name': '款式', 'value_name': value}]} for value in ['A', 'B']],
    })


def test_reject_duplicate_sku_combination_even_when_counts_match():
    body = request()
    assert body.validate_spec_consistency() == []
    body.spec_prices[1].sell_properties[0].value_name = 'A'
    assert any('组合重复' in p for p in body.validate_spec_consistency())


def test_reject_unknown_sku_spec_value():
    body = request()
    body.spec_prices[1].sell_properties[0].value_name = 'C'
    assert any('未声明' in p for p in body.validate_spec_consistency())
