import pytest
import json
from gltest import *
from conftest import sim_installMocks


@pytest.fixture
def contract(direct_deploy):
    return direct_deploy("contracts/insurance_weather_crop_x.py")


def test_initial_state_and_domains(contract, direct_vm, direct_alice, direct_bob):
    # Initial state assertions
    assert contract.get_policy_count() == 0
    owner_str = contract.get_owner().lower()
    expected_sender = direct_vm.sender.hex().lower() if isinstance(direct_vm.sender, bytes) else str(direct_vm.sender).lower()
    if not expected_sender.startswith("0x"):
        expected_sender = "0x" + expected_sender
    assert owner_str == expected_sender

    # Default canonical meteorological domains
    assert contract.is_weather_domain_allowed("open-meteo.com") is True
    assert contract.is_weather_domain_allowed("api.open-meteo.com") is True
    assert contract.is_weather_domain_allowed("archive-api.open-meteo.com") is True
    assert contract.is_weather_domain_allowed("weather.gov") is True
    assert contract.is_weather_domain_allowed("api.weather.gov") is True
    assert contract.is_weather_domain_allowed("noaa.gov") is True
    assert contract.is_weather_domain_allowed("www.noaa.gov") is True
    assert contract.is_weather_domain_allowed("ecmwf.int") is True
    assert contract.is_weather_domain_allowed("mock-weather.genlayer.com") is True
    assert contract.is_weather_domain_allowed("untrusted-fake-weather.org") is False

    # Owner adds custom allowed weather observation domain
    contract.add_allowed_weather_domain("agrometeo.ch")
    assert contract.is_weather_domain_allowed("agrometeo.ch") is True

    # Owner revokes custom allowed weather observation domain
    contract.remove_allowed_weather_domain("agrometeo.ch")
    assert contract.is_weather_domain_allowed("agrometeo.ch") is False

    # Non-owner cannot add weather domain
    direct_vm.sender = direct_bob
    with pytest.raises(Exception, match="Only owner can add allowed weather domains"):
        contract.add_allowed_weather_domain("fraud-meteo.net")

    # Non-owner cannot remove weather domain
    with pytest.raises(Exception, match="Only owner can remove allowed weather domains"):
        contract.remove_allowed_weather_domain("noaa.gov")


def test_create_policy_success(contract, direct_vm, direct_alice, direct_bob):
    direct_vm.sender = direct_bob
    direct_vm.value = 5000  # Insurer locks 5000 GEN coverage

    pid = contract.create_policy(
        farmer=direct_alice,
        risk_type="DROUGHT",
        station_id="STATION-VN-MEKONG-01",
        trigger_threshold="Rainfall < 10mm for 30 consecutive days during crop vegetative stage",
        weather_data_url="https://api.open-meteo.com/v1/forecast?latitude=10.0&longitude=105.5&station_id=STATION-VN-MEKONG-01",
        policy_duration_sec=86400 * 30
    )

    assert pid == "1"
    assert contract.get_policy_count() == 1

    p = json.loads(contract.get_policy("1"))
    assert p["policy_id"] == "1"
    assert p["farmer"] == direct_alice.as_hex.lower()
    assert p["insurer"] == direct_bob.as_hex.lower()
    assert p["risk_type"] == "DROUGHT"
    assert p["station_id"] == "STATION-VN-MEKONG-01"
    assert p["coverage_amount"] == "5000"
    assert p["premium_paid"] == "0"
    assert p["status"] == "ACTIVE"
    assert p["verdict"] == "PENDING"
    assert p["farmer_payout"] == "0"
    assert p["insurer_payout"] == "0"


def test_create_policy_validations(contract, direct_vm, direct_alice, direct_bob):
    direct_vm.sender = direct_bob

    # 1. Zero coverage funding
    direct_vm.value = 0
    with pytest.raises(Exception, match="Coverage funding must be greater than 0 GEN"):
        contract.create_policy(
            farmer=direct_alice,
            risk_type="DROUGHT",
            station_id="STATION-VN-01",
            trigger_threshold="Rainfall < 10mm",
            weather_data_url="https://api.open-meteo.com/v1/forecast",
            policy_duration_sec=86400
        )

    # 2. Farmer and Insurer cannot be the same address
    direct_vm.value = 2000
    with pytest.raises(Exception, match="Farmer and insurer cannot be the same address"):
        contract.create_policy(
            farmer=direct_bob,
            risk_type="DROUGHT",
            station_id="STATION-VN-01",
            trigger_threshold="Rainfall < 10mm",
            weather_data_url="https://api.open-meteo.com/v1/forecast",
            policy_duration_sec=86400
        )

    # 3. Invalid risk type
    with pytest.raises(Exception, match="risk_type must be either 'DROUGHT' or 'FLOOD'"):
        contract.create_policy(
            farmer=direct_alice,
            risk_type="EARTHQUAKE",
            station_id="STATION-VN-01",
            trigger_threshold="Rainfall < 10mm",
            weather_data_url="https://api.open-meteo.com/v1/forecast",
            policy_duration_sec=86400
        )

    # 4. Station ID too short
    with pytest.raises(Exception, match="station_id must be valid"):
        contract.create_policy(
            farmer=direct_alice,
            risk_type="DROUGHT",
            station_id="AB",
            trigger_threshold="Rainfall < 10mm",
            weather_data_url="https://api.open-meteo.com/v1/forecast",
            policy_duration_sec=86400
        )

    # 5. Trigger threshold too short
    with pytest.raises(Exception, match="trigger_threshold description is too short"):
        contract.create_policy(
            farmer=direct_alice,
            risk_type="DROUGHT",
            station_id="STATION-VN-01",
            trigger_threshold="Rain",
            weather_data_url="https://api.open-meteo.com/v1/forecast",
            policy_duration_sec=86400
        )

    # 6. Invalid URL protocol
    with pytest.raises(Exception, match="weather_data_url must start with http:// or https://"):
        contract.create_policy(
            farmer=direct_alice,
            risk_type="DROUGHT",
            station_id="STATION-VN-01",
            trigger_threshold="Rainfall < 10mm for 20 days",
            weather_data_url="ftp://api.open-meteo.com/v1/forecast",
            policy_duration_sec=86400
        )

    # 7. Weather domain not whitelisted
    with pytest.raises(Exception, match="is not in the allowed whitelist"):
        contract.create_policy(
            farmer=direct_alice,
            risk_type="FLOOD",
            station_id="STATION-VN-01",
            trigger_threshold="Precipitation > 300mm in 24 hours",
            weather_data_url="https://unauthorized-weather-scam.io/data",
            policy_duration_sec=86400
        )


def test_pay_premium_success(contract, direct_vm, direct_alice, direct_bob):
    # Insurer Bob creates policy
    direct_vm.sender = direct_bob
    direct_vm.value = 4000
    pid = contract.create_policy(
        farmer=direct_alice,
        risk_type="FLOOD",
        station_id="STATION-DANANG-02",
        trigger_threshold="Daily precipitation exceeds 250mm within a 48 hour window",
        weather_data_url="https://api.weather.gov/stations/DANANG02/observations",
        policy_duration_sec=86400 * 14
    )

    # Farmer Alice pays premium
    direct_vm.sender = direct_alice
    direct_vm.value = 400
    contract.pay_premium(pid)

    p = json.loads(contract.get_policy(pid))
    assert p["premium_paid"] == "400"
    assert p["status"] == "ACTIVE"


def test_pay_premium_validations(contract, direct_vm, direct_alice, direct_bob, direct_charlie):
    direct_vm.sender = direct_bob
    direct_vm.value = 3000
    pid = contract.create_policy(
        farmer=direct_alice,
        risk_type="DROUGHT",
        station_id="STATION-CENTRAL-01",
        trigger_threshold="Consecutive dry days >= 21 days with temperature > 38C",
        weather_data_url="https://api.open-meteo.com/v1/archive",
        policy_duration_sec=86400 * 30
    )

    # 1. Non-farmer cannot pay premium
    direct_vm.sender = direct_charlie
    direct_vm.value = 300
    with pytest.raises(Exception, match="Only designated farmer can pay policy premium"):
        contract.pay_premium(pid)

    # 2. Non-existent policy
    direct_vm.sender = direct_alice
    with pytest.raises(Exception, match="Policy not found"):
        contract.pay_premium("999")

    # 3. Zero premium payment
    direct_vm.value = 0
    with pytest.raises(Exception, match="Premium must be greater than 0 GEN"):
        contract.pay_premium(pid)


def test_cancel_unactivated_policy_success(contract, direct_vm, direct_alice, direct_bob):
    direct_vm.sender = direct_bob
    direct_vm.value = 6000
    pid = contract.create_policy(
        farmer=direct_alice,
        risk_type="DROUGHT",
        station_id="STATION-HIGHLAND-05",
        trigger_threshold="Cumulative rainfall below 20mm over 45 days",
        weather_data_url="https://api.open-meteo.com/v1/forecast",
        policy_duration_sec=86400 * 45
    )

    # Farmer has not paid premium; Insurer cancels unactivated policy
    direct_vm.sender = direct_bob
    contract.cancel_unactivated_policy(pid)

    p = json.loads(contract.get_policy(pid))
    assert p["status"] == "CANCELLED"
    assert "Policy cancelled by insurer before farmer premium activation" in p["reason"]


def test_cancel_unactivated_policy_validations(contract, direct_vm, direct_alice, direct_bob):
    direct_vm.sender = direct_bob
    direct_vm.value = 3500
    pid = contract.create_policy(
        farmer=direct_alice,
        risk_type="DROUGHT",
        station_id="STATION-DELTA-01",
        trigger_threshold="Soil moisture index below 10% for 20 days",
        weather_data_url="https://archive-api.open-meteo.com/v1/archive",
        policy_duration_sec=86400 * 20
    )

    # 1. Non-insurer caller cannot cancel
    direct_vm.sender = direct_alice
    with pytest.raises(Exception, match="Only insurer can cancel unactivated policy"):
        contract.cancel_unactivated_policy(pid)

    # 2. Non-existent policy
    direct_vm.sender = direct_bob
    with pytest.raises(Exception, match="Policy not found"):
        contract.cancel_unactivated_policy("999")

    # 3. Once farmer pays premium, insurer can no longer cancel
    direct_vm.sender = direct_alice
    direct_vm.value = 350
    contract.pay_premium(pid)

    direct_vm.sender = direct_bob
    with pytest.raises(Exception, match="Cannot cancel policy once farmer has paid premium"):
        contract.cancel_unactivated_policy(pid)


def test_adjudicate_validation_failures(contract, direct_vm, direct_alice, direct_bob):
    from datetime import datetime, timezone, timedelta
    t_start = datetime(2026, 10, 15, 12, 0, 0, tzinfo=timezone.utc)
    direct_vm.warp(t_start.isoformat())

    direct_vm.sender = direct_bob
    direct_vm.value = 5000
    pid = contract.create_policy(
        farmer=direct_alice,
        risk_type="DROUGHT",
        station_id="STATION-NORTH-01",
        trigger_threshold="Rainfall < 5mm for 30 consecutive days",
        weather_data_url="https://api.open-meteo.com/v1/forecast",
        policy_duration_sec=86400 * 30
    )

    # 1. Non-existent policy
    with pytest.raises(Exception, match="Policy not found"):
        contract.adjudicate_weather_claim("999")

    # 2. Unactivated policy (farmer hasn't paid premium)
    with pytest.raises(Exception, match="Policy premium has not been paid yet; policy is unactivated"):
        contract.adjudicate_weather_claim(pid)

    # Farmer activates policy
    direct_vm.sender = direct_alice
    direct_vm.value = 500
    contract.pay_premium(pid)

    # 3. Premature adjudication before coverage duration concludes
    with pytest.raises(Exception, match="Policy coverage window is still ongoing"):
        contract.adjudicate_weather_claim(pid)


def test_adjudicate_total_loss_triggered(contract, direct_vm, direct_alice, direct_bob):
    from datetime import datetime, timezone, timedelta
    t_start = datetime(2026, 10, 15, 12, 0, 0, tzinfo=timezone.utc)
    direct_vm.warp(t_start.isoformat())

    direct_vm.sender = direct_bob
    direct_vm.value = 10000  # 10,000 GEN coverage
    pid = contract.create_policy(
        farmer=direct_alice,
        risk_type="DROUGHT",
        station_id="STATION-MEKONG-ALPHA",
        trigger_threshold="Precipitation = 0mm for 35 consecutive days with max temp > 39C",
        weather_data_url="https://api.open-meteo.com/v1/forecast?station=STATION-MEKONG-ALPHA",
        policy_duration_sec=86400 * 30
    )

    # Farmer pays 1,000 GEN premium
    direct_vm.sender = direct_alice
    direct_vm.value = 1000
    contract.pay_premium(pid)

    # Warp past policy monitoring end (31 days later)
    direct_vm.warp((t_start + timedelta(days=31)).isoformat())

    # Install Mocks: Catastrophic drought observed
    sim_installMocks({
        "web_mocks": {
            ".*open-meteo.com.*": {
                "status": 200,
                "body": "Official Meteorological Record for STATION-MEKONG-ALPHA: 38 consecutive days with 0.0mm rainfall recorded. Maximum daily temperatures exceeded 40.2C. Catastrophic drought index D4 reached."
            }
        },
        "llm_mocks": {
            ".*": {
                "verdict": "TOTAL_LOSS_TRIGGERED",
                "confidence": 99,
                "reason": "Official meteorological station confirmed 38 consecutive days zero rainfall, breaching catastrophic drought threshold."
            }
        }
    }, vm=direct_vm)

    contract.adjudicate_weather_claim(pid)

    p = json.loads(contract.get_policy(pid))
    assert p["status"] == "SETTLED"
    assert p["verdict"] == "TOTAL_LOSS_TRIGGERED"
    # Farmer receives 100% coverage (10,000) + premium refunded (1,000) = 11,000 GEN
    assert p["farmer_payout"] == "11000"
    assert p["insurer_payout"] == "0"
    assert "breaching catastrophic drought threshold" in p["reason"]

    # Double adjudication fails
    with pytest.raises(Exception, match="Policy is already settled or cancelled"):
        contract.adjudicate_weather_claim(pid)


def test_adjudicate_partial_loss_triggered(contract, direct_vm, direct_alice, direct_bob):
    from datetime import datetime, timezone, timedelta
    t_start = datetime(2026, 10, 15, 12, 0, 0, tzinfo=timezone.utc)
    direct_vm.warp(t_start.isoformat())

    direct_vm.sender = direct_bob
    direct_vm.value = 8000  # 8,000 GEN coverage
    pid = contract.create_policy(
        farmer=direct_alice,
        risk_type="FLOOD",
        station_id="STATION-HUE-FLOOD-09",
        trigger_threshold="Rainfall exceeds 400mm in 72 hours",
        weather_data_url="https://api.weather.gov/stations/STATION-HUE-FLOOD-09/observations",
        policy_duration_sec=86400 * 10
    )

    # Farmer pays 800 GEN premium
    direct_vm.sender = direct_alice
    direct_vm.value = 800
    contract.pay_premium(pid)

    direct_vm.warp((t_start + timedelta(days=12)).isoformat())

    # Install Mocks: Moderate localized flood touching threshold
    sim_installMocks({
        "web_mocks": {
            ".*weather.gov.*": {
                "status": 200,
                "body": "Meteorological observation for STATION-HUE-FLOOD-09: 72-hour cumulative precipitation recorded at 385mm, causing significant localized riverbank breach and moderate crop field waterlogging."
            }
        },
        "llm_mocks": {
            ".*": {
                "verdict": "PARTIAL_LOSS_TRIGGERED",
                "confidence": 92,
                "reason": "Severe rainfall near threshold causing localized field inundation qualifying for partial loss indemnity."
            }
        }
    }, vm=direct_vm)

    contract.adjudicate_weather_claim(pid)

    p = json.loads(contract.get_policy(pid))
    assert p["status"] == "SETTLED"
    assert p["verdict"] == "PARTIAL_LOSS_TRIGGERED"
    # Farmer receives 50% coverage (4,000) + premium (800) = 4,800 GEN
    # Insurer receives remaining 50% coverage = 4,000 GEN
    assert p["farmer_payout"] == "4800"
    assert p["insurer_payout"] == "4000"
    assert "partial loss indemnity" in p["reason"]


def test_adjudicate_normal_conditions(contract, direct_vm, direct_alice, direct_bob):
    from datetime import datetime, timezone, timedelta
    t_start = datetime(2026, 10, 15, 12, 0, 0, tzinfo=timezone.utc)
    direct_vm.warp(t_start.isoformat())

    direct_vm.sender = direct_bob
    direct_vm.value = 6000
    pid = contract.create_policy(
        farmer=direct_alice,
        risk_type="DROUGHT",
        station_id="STATION-RED-RIVER-04",
        trigger_threshold="Rainfall < 15mm for 25 consecutive days",
        weather_data_url="https://ecmwf.int/forecasts/stations/red-river-04",
        policy_duration_sec=86400 * 20
    )

    direct_vm.sender = direct_alice
    direct_vm.value = 600
    contract.pay_premium(pid)

    direct_vm.warp((t_start + timedelta(days=22)).isoformat())

    # Install Mocks: Normal seasonal weather
    sim_installMocks({
        "web_mocks": {
            ".*ecmwf.int.*": {
                "status": 200,
                "body": "ECMWF Official Observation: Station RED-RIVER-04 recorded steady precipitation with regular rain events every 4-6 days (total 112mm). Soil moisture within optimal range."
            }
        },
        "llm_mocks": {
            ".*": {
                "verdict": "NORMAL_CONDITIONS",
                "confidence": 97,
                "reason": "Meteorological parameters remained within normal seasonal range with ample rainfall."
            }
        }
    }, vm=direct_vm)

    contract.adjudicate_weather_claim(pid)

    p = json.loads(contract.get_policy(pid))
    assert p["status"] == "SETTLED"
    assert p["verdict"] == "NORMAL_CONDITIONS"
    # Insurer receives total coverage (6,000) + earned premium (600) = 6,600 GEN
    assert p["farmer_payout"] == "0"
    assert p["insurer_payout"] == "6600"
    assert "normal seasonal range" in p["reason"]


def test_adjudicate_offline_or_404_fallback(contract, direct_vm, direct_alice, direct_bob):
    from datetime import datetime, timezone, timedelta
    t_start = datetime(2026, 10, 15, 12, 0, 0, tzinfo=timezone.utc)
    direct_vm.warp(t_start.isoformat())

    direct_vm.sender = direct_bob
    direct_vm.value = 5000
    pid = contract.create_policy(
        farmer=direct_alice,
        risk_type="DROUGHT",
        station_id="STATION-OFFLINE-01",
        trigger_threshold="Rainfall < 10mm for 20 days",
        weather_data_url="https://api.weather.gov/offline-station-data",
        policy_duration_sec=86400 * 20
    )

    direct_vm.sender = direct_alice
    direct_vm.value = 500
    contract.pay_premium(pid)

    direct_vm.warp((t_start + timedelta(days=21)).isoformat())

    # Web mock returns 404
    sim_installMocks({
        "web_mocks": {
            ".*weather.gov.*": {
                "status": 404,
                "body": "404 Not Found: Meteorological station sensor decommissioned."
            }
        }
    }, vm=direct_vm)

    contract.adjudicate_weather_claim(pid)

    p = json.loads(contract.get_policy(pid))
    assert p["status"] == "SETTLED"
    assert p["verdict"] == "NORMAL_CONDITIONS"
    assert "offline, blank, or returned 404" in p["reason"]
    assert p["insurer_payout"] == "5500"
    assert p["farmer_payout"] == "0"
