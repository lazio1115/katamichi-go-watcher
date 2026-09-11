from watcher.normalize import make_key, normalize, parse_period, split_car, split_shop


def test_nfkc_folds_width_in_both_directions():
    assert normalize("ＡＢＣ１２３") == "ABC123"
    assert normalize("ﾊｲｴｰｽﾊﾞﾝ") == "ハイエースバン"


def test_collapses_whitespace_and_strips_backslashes():
    assert normalize("  ヤリス　　HV ") == "ヤリス HV"
    assert normalize("\\ルーミー") == "ルーミー"
    assert normalize(None) == ""


def test_split_car_label_forms():
    assert split_car("ヤリス　車両番号3735") == ("ヤリス", "3735")
    assert split_car("アクア 車輛番号 3628") == ("アクア", "3628")
    assert split_car("シエンタ 登録番号 42") == ("シエンタ", "42")


def test_split_car_license_plate():
    assert split_car("ヤリス　青森501わ3843") == ("ヤリス", "青森501わ3843")
    assert split_car("アクア いわき500わ4222") == ("アクア", "いわき500わ4222")


def test_split_car_plate_without_a_separator():
    assert split_car("ヤリス八戸500わ8598") == ("ヤリス", "八戸500わ8598")
    assert split_car("ルーミー白河500わ612") == ("ルーミー", "白河500わ612")


def test_split_car_label_and_plate_together():
    assert split_car("カローラHV　車両番号山形300わ2156") == ("カローラHV", "山形300わ2156")


def test_split_car_plate_with_middle_dot_padding():
    assert split_car("ヤリスHV　仙台502わ･169") == ("ヤリスHV", "仙台502わ・169")


def test_split_car_bare_trailing_number():
    assert split_car("アルファードＨＥＶ1084") == ("アルファードHEV", "1084")
    assert split_car("ルーミー　3784") == ("ルーミー", "3784")


def test_split_car_without_number():
    # NFKC folds full-width parentheses to half-width.
    assert split_car("乗用車（下田駅前店・伊東駅前店以外の店舗返却）") == (
        "乗用車(下田駅前店・伊東駅前店以外の店舗返却)",
        "",
    )
    assert split_car("ハイエースバン") == ("ハイエースバン", "")
    assert split_car("コンパクトカー") == ("コンパクトカー", "")


def test_split_shop():
    assert split_shop("トヨタレンタリース宮城 仙台空港店") == ("トヨタレンタリース宮城", "仙台空港店")
    assert split_shop("トヨタレンタリース山形") == ("トヨタレンタリース山形", "")


def test_parse_period_carries_year_from_start():
    assert parse_period("2026年9月7日 ～ 9月9日") == ("2026-09-07", "2026-09-09")
    assert parse_period("2026年8月14日 ～ 2026年8月21日") == ("2026-08-14", "2026-08-21")


def test_parse_period_rolls_over_new_year():
    assert parse_period("2026年12月30日 ～ 1月3日") == ("2026-12-30", "2027-01-03")


def test_parse_period_unparsable():
    assert parse_period("未定") == ("", "")


def test_key_is_stable_across_formatting_noise():
    a = make_key("トヨタレンタリース宮城", "卸町店", "トヨタレンタリース青森", "ヤリス", "3843", "2026-08-14", "2026-08-21")
    b = make_key("トヨタレンタリース宮城　", " 卸町店", "トヨタレンタリース青森", "ヤリス", "3843", "2026-08-14", "2026-08-21")
    assert a == b


def test_key_separates_same_car_in_different_periods():
    a = make_key("A", "B", "C", "ヤリス", "3843", "2026-08-14", "2026-08-21")
    b = make_key("A", "B", "C", "ヤリス", "3843", "2026-09-14", "2026-09-21")
    assert a != b
