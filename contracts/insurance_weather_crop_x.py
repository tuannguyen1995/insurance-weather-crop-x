# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
from genlayer import *
from dataclasses import dataclass
import json


try:
    gl.UserError = gl.vm.UserError
except Exception:
    pass


def _addr_str(addr: Address) -> str:
    """Safely format an Address instance into a lowercase hex string."""
    try:
        return addr.as_hex.lower()
    except Exception:
        return str(addr).lower()


def _get_sender() -> Address:
    """Safely obtain transaction sender across GenVM runtime versions."""
    try:
        return gl.message.sender
    except Exception:
        try:
            return gl.message.sender_address
        except Exception:
            try:
                if hasattr(gl, "message_raw") and isinstance(gl.message_raw, dict):
                    sender_raw = gl.message_raw.get("from") or gl.message_raw.get("sender")
                    if sender_raw:
                        return Address(str(sender_raw))
            except Exception:
                pass
            raise gl.UserError("Cannot resolve sender address.")


def _safe_transfer(recipient: Address, amount: bigint) -> None:
    """Safely disburse native GEN to an address using official GenLayer SDK pattern."""
    if amount <= bigint(0):
        return
    gl.get_contract_at(recipient).emit_transfer(value=u256(int(amount)))


DEFAULT_WEATHER_DOMAINS = (
    "open-meteo.com",
    "archive-api.open-meteo.com",
    "api.open-meteo.com",
    "weather.gov",
    "api.weather.gov",
    "noaa.gov",
    "www.noaa.gov",
    "ecmwf.int",
    "mock-weather.genlayer.com",
)


def _parse_url_host(raw_url: str) -> str:
    """Extract and validate normalized hostname from URL."""
    clean = raw_url.strip()
    if "?" in clean:
        clean = clean.split("?")[0]
    if "#" in clean:
        clean = clean.split("#")[0]
    clean = clean.strip()

    if clean.startswith("https://"):
        rest = clean[8:]
    elif clean.startswith("http://"):
        rest = clean[7:]
    else:
        raise gl.UserError("URL must begin with http:// or https://")

    host = rest.split("/", 1)[0].strip().lower()
    if ":" in host:
        host = host.split(":")[0].strip()
    if not host:
        raise gl.UserError("Invalid URL: missing host")
    return host


@allow_storage
@dataclass
class CropPolicy:
    policy_id: str
    farmer: Address
    insurer: Address
    risk_type: str              # "DROUGHT" or "FLOOD"
    station_id: str             # Certified weather station identifier or geo-tag
    trigger_threshold: str      # Condition description (e.g. "rainfall < 15mm for 21 consecutive days")
    weather_data_url: str       # Canonical weather API or observation report URL
    premium_paid: bigint        # Farmer's premium deposit
    coverage_amount: bigint     # Total insured payout locked by underwriter
    status: str                 # "ACTIVE", "SETTLED", "CANCELLED"
    verdict: str                # "PENDING", "TOTAL_LOSS_TRIGGERED", "PARTIAL_LOSS_TRIGGERED", "NORMAL_CONDITIONS", "EVIDENCE_UNAVAILABLE"
    farmer_payout: bigint
    insurer_payout: bigint
    reason: str                 # Consensus evaluation rationale
    policy_start: bigint        # Monitoring window start timestamp
    policy_end: bigint          # Monitoring window end timestamp
    created_at: bigint
    resolved_at: bigint


class Contract(gl.Contract):
    """
    InsuranceWeatherCropX: Parametric Extreme Weather Drought & Flood Insurance Protocol
    Track: Prediction Markets & Real-World Settlement
    """
    owner: Address
    policy_count: bigint
    policies: TreeMap[str, CropPolicy]
    custom_allowed_weather_domains: TreeMap[str, bool]

    def __init__(self):
        # GenVM automatically initializes TreeMap storage fields to empty.
        self.owner = _get_sender()
        self.policy_count = bigint(0)

    def _get_current_timestamp(self) -> bigint:
        """Derive trusted deterministic execution timestamp from GenLayer transaction context."""
        try:
            from datetime import datetime
            dt_raw = getattr(gl.message, "datetime", None)
            if dt_raw is None and hasattr(gl, "message_raw") and isinstance(gl.message_raw, dict):
                dt_raw = gl.message_raw.get("datetime")
            if dt_raw:
                dt_str = str(dt_raw).strip().replace("Z", "+00:00")
                dt = datetime.fromisoformat(dt_str)
                ts = int(dt.timestamp())
                if ts > 0:
                    return bigint(ts)
        except Exception:
            pass

        try:
            if hasattr(gl, "block") and hasattr(gl.block, "timestamp"):
                ts = int(gl.block.timestamp)
                if ts > 0:
                    return bigint(ts)
        except Exception:
            pass

        return bigint(0)

    def _parse_llm_json(self, text: str) -> dict:
        """Safely parse LLM responses, stripping markdown wrappers if present."""
        try:
            cleaned = str(text).strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            elif cleaned.startswith("```"):
                cleaned = cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            return json.loads(cleaned.strip())
        except Exception as e:
            return {
                "verdict": "EVIDENCE_UNAVAILABLE",
                "confidence": 0,
                "reason": f"Failed to parse LLM JSON: {str(e)[:100]}"
            }

    @gl.public.write
    def add_allowed_weather_domain(self, domain: str) -> None:
        """Owner can add new trusted weather observation domains."""
        if _addr_str(_get_sender()) != _addr_str(self.owner):
            raise gl.UserError("Only owner can add allowed weather domains.")
        clean = domain.strip().lower()
        if len(clean) < 3:
            raise gl.UserError("Invalid domain name.")
        self.custom_allowed_weather_domains[clean] = True

    @gl.public.write
    def remove_allowed_weather_domain(self, domain: str) -> None:
        """Owner can revoke custom or default allowed weather domains."""
        if _addr_str(_get_sender()) != _addr_str(self.owner):
            raise gl.UserError("Only owner can remove allowed weather domains.")
        clean = domain.strip().lower()
        self.custom_allowed_weather_domains[clean] = False

    @gl.public.view
    def is_weather_domain_allowed(self, domain: str) -> bool:
        """Check if weather observation host is whitelisted."""
        clean = domain.strip().lower()
        if clean in DEFAULT_WEATHER_DOMAINS:
            try:
                if clean in self.custom_allowed_weather_domains and not self.custom_allowed_weather_domains[clean]:
                    return False
            except Exception:
                pass
            return True
        try:
            return bool(self.custom_allowed_weather_domains[clean])
        except Exception:
            return False

    @gl.public.write.payable
    def create_policy(
        self,
        farmer: Address,
        risk_type: str,
        station_id: str,
        trigger_threshold: str,
        weather_data_url: str,
        policy_duration_sec: int
    ) -> str:
        """
        Insurer (Underwriter) creates an insured policy and locks total coverage payout in escrow.
        Farmer will subsequently pay their premium to activate it.
        """
        coverage = bigint(gl.message.value)
        if coverage <= bigint(0):
            raise gl.UserError("Coverage funding must be greater than 0 GEN.")

        if _addr_str(farmer) == _addr_str(_get_sender()):
            raise gl.UserError("Farmer and insurer cannot be the same address.")

        clean_risk = risk_type.strip().upper()
        if clean_risk not in ("DROUGHT", "FLOOD"):
            raise gl.UserError("risk_type must be either 'DROUGHT' or 'FLOOD'.")

        clean_station = station_id.strip().upper()
        clean_trig = trigger_threshold.strip()
        clean_url = weather_data_url.strip()

        if len(clean_station) < 3:
            raise gl.UserError("station_id must be valid.")
        if len(clean_trig) < 5:
            raise gl.UserError("trigger_threshold description is too short.")

        if not (clean_url.startswith("http://") or clean_url.startswith("https://")):
            raise gl.UserError("weather_data_url must start with http:// or https://")

        # Canonical Domain Whitelist Check
        host = _parse_url_host(clean_url)
        if not self.is_weather_domain_allowed(host):
            raise gl.UserError(f"Weather domain '{host}' is not in the allowed whitelist.")

        now_ts = self._get_current_timestamp()
        duration = bigint(policy_duration_sec if policy_duration_sec >= 86400 else 86400)
        end_ts = now_ts + duration if now_ts > bigint(0) else bigint(86400 * 30)

        self.policy_count += bigint(1)
        pid = str(self.policy_count)

        self.policies[pid] = CropPolicy(
            policy_id=pid,
            farmer=farmer,
            insurer=_get_sender(),
            risk_type=clean_risk,
            station_id=clean_station,
            trigger_threshold=clean_trig,
            weather_data_url=clean_url,
            premium_paid=bigint(0),
            coverage_amount=coverage,
            status="ACTIVE",
            verdict="PENDING",
            farmer_payout=bigint(0),
            insurer_payout=bigint(0),
            reason="Policy funded by underwriter. Ready for monitoring.",
            policy_start=now_ts,
            policy_end=end_ts,
            created_at=now_ts if now_ts > bigint(0) else self.policy_count,
            resolved_at=bigint(0)
        )

        return pid

    @gl.public.write.payable
    def pay_premium(self, policy_id: str) -> None:
        """
        Farmer pays their policy premium deposit into the escrow contract.
        """
        if policy_id not in self.policies:
            raise gl.UserError("Policy not found.")

        policy = self.policies[policy_id]
        if _addr_str(_get_sender()) != _addr_str(policy.farmer):
            raise gl.UserError("Only designated farmer can pay policy premium.")

        if policy.status != "ACTIVE":
            raise gl.UserError("Policy is not in ACTIVE state.")

        prem = bigint(gl.message.value)
        if prem <= bigint(0):
            raise gl.UserError("Premium must be greater than 0 GEN.")

        policy.premium_paid += prem
        self.policies[policy_id] = policy

    @gl.public.write
    def update_weather_data_url(self, policy_id: str, new_weather_data_url: str) -> None:
        """
        Allows insurer or farmer to update weather data URL if original endpoint is offline/deprecated.
        Preserves policy for safe retry with verified meteorological domain.
        """
        if policy_id not in self.policies:
            raise gl.UserError("Policy not found.")

        policy = self.policies[policy_id]
        sender = _addr_str(_get_sender())
        if sender != _addr_str(policy.insurer) and sender != _addr_str(policy.farmer):
            raise gl.UserError("Only policy insurer or farmer can update weather data URL.")

        if policy.status != "ACTIVE":
            raise gl.UserError("Cannot update URL for settled or cancelled policy.")

        clean_url = new_weather_data_url.strip()
        if not (clean_url.startswith("http://") or clean_url.startswith("https://")):
            raise gl.UserError("weather_data_url must start with http:// or https://")

        host = _parse_url_host(clean_url)
        if not self.is_weather_domain_allowed(host):
            raise gl.UserError(f"Weather domain '{host}' is not in the allowed whitelist.")

        policy.weather_data_url = clean_url
        policy.reason = f"Weather data URL updated by authorized party to host {host}. Ready for retry."
        self.policies[policy_id] = policy

    @gl.public.write
    def adjudicate_weather_claim(self, policy_id: str) -> None:
        """
        Validators scrape official weather observation data directly on-chain,
        verify weather parameters against threshold, and execute discrete settlement.
        If weather evidence is offline, blank, 404, or unparseable, the policy remains ACTIVE
        with zero disbursement, preserving all escrow funds for safe retry.
        """
        if policy_id not in self.policies:
            raise gl.UserError("Policy not found.")

        policy = self.policies[policy_id]
        if policy.status != "ACTIVE":
            raise gl.UserError("Policy is already settled or cancelled.")

        if policy.premium_paid <= bigint(0):
            raise gl.UserError("Policy premium has not been paid yet; policy is unactivated.")

        now_ts = self._get_current_timestamp()
        if now_ts > bigint(0) and now_ts < policy.policy_end:
            raise gl.UserError("Policy coverage window is still ongoing; cannot prematurely adjudicate.")

        risk_local = str(policy.risk_type)
        station_local = str(policy.station_id)
        trig_local = str(policy.trigger_threshold)
        url_local = str(policy.weather_data_url)

        def leader_fn():
            web_content = ""
            try:
                res = gl.nondet.web.render(url_local, mode="text")
                if hasattr(res, "content"):
                    web_content = res.content
                elif isinstance(res, dict) and "body" in res:
                    web_content = res["body"]
                else:
                    web_content = str(res)
            except Exception:
                web_content = ""

            lower_web = web_content[:500].lower() if web_content else ""
            if len(web_content.strip()) < 15 or "404 not found" in lower_web or "error" in lower_web:
                return {
                    "verdict": "EVIDENCE_UNAVAILABLE",
                    "confidence": 0,
                    "reason": "Weather observation endpoint is offline, blank, or returned 404/error."
                }

            snippet = web_content[:4000]

            prompt = f"""You are the Autonomous Parametric Agricultural Weather Insurance Arbiter on GenLayer.
Evaluate the official meteorological observation data for STATION: {station_local} regarding RISK: {risk_local}.
Assess whether the observed weather data breached the contractual parametric trigger threshold.

CONTRACT PARAMETRIC TRIGGER CRITERIA:
\"\"\"
{trig_local}
\"\"\"

OBSERVED METEOROLOGICAL OBSERVATION DATA:
\"\"\"
{snippet}
\"\"\"

DISCRETE CLASSIFICATION RULES:
- "TOTAL_LOSS_TRIGGERED": Observation data clearly confirms extreme disaster conditions meeting or exceeding the trigger threshold (e.g. continuous severe drought with 0 rainfall or extreme flood volume), destroying seasonal crops.
- "PARTIAL_LOSS_TRIGGERED": Severe weather occurred near or partially touching the threshold, causing substantial localized yield reduction.
- "NORMAL_CONDITIONS": Observation data clearly confirms weather parameters stayed within normal seasonal variance; threshold was not breached.
- "EVIDENCE_UNAVAILABLE": Meteorological observation data is corrupted, contradictory, incomplete, or unparseable.

OUTPUT FORMAT:
Respond ONLY with a VALID JSON object (no markdown, no backticks):
{{
  "verdict": "TOTAL_LOSS_TRIGGERED" | "PARTIAL_LOSS_TRIGGERED" | "NORMAL_CONDITIONS" | "EVIDENCE_UNAVAILABLE",
  "confidence": <integer from 0 to 100>,
  "reason": "<concise explanation max 220 characters>"
}}"""

            try:
                raw_res = gl.nondet.exec_prompt(prompt, response_format="json")
                parsed = None
                if isinstance(raw_res, dict):
                    parsed = raw_res
                elif hasattr(raw_res, "content") and isinstance(raw_res.content, dict):
                    parsed = raw_res.content
                else:
                    text = raw_res.content if hasattr(raw_res, "content") else str(raw_res)
                    cleaned = str(text).strip()
                    if cleaned.startswith("```json"):
                        cleaned = cleaned[7:]
                    elif cleaned.startswith("```"):
                        cleaned = cleaned[3:]
                    if cleaned.endswith("```"):
                        cleaned = cleaned[:-3]
                    parsed = json.loads(cleaned.strip())

                verdict_candidate = str(parsed.get("verdict", "EVIDENCE_UNAVAILABLE")).strip().upper()
                valid_verdicts = ("TOTAL_LOSS_TRIGGERED", "PARTIAL_LOSS_TRIGGERED", "NORMAL_CONDITIONS", "EVIDENCE_UNAVAILABLE")
                if verdict_candidate not in valid_verdicts:
                    verdict_candidate = "EVIDENCE_UNAVAILABLE"

                try:
                    conf = int(parsed.get("confidence", 0))
                    conf = max(0, min(100, conf))
                except Exception:
                    conf = 50

                reason_str = str(parsed.get("reason", "Weather audited by autonomous jury."))[:220]

                return {
                    "verdict": verdict_candidate,
                    "confidence": conf,
                    "reason": reason_str
                }
            except Exception as e:
                return {
                    "verdict": "EVIDENCE_UNAVAILABLE",
                    "confidence": 0,
                    "reason": f"Audit execution error: {str(e)[:100]}"
                }

        def validator_fn(leader_res) -> bool:
            if not isinstance(leader_res, gl.vm.Return):
                return False
            leader = leader_res.calldata
            if not isinstance(leader, dict) or "verdict" not in leader:
                return False

            valid_verdicts = ("TOTAL_LOSS_TRIGGERED", "PARTIAL_LOSS_TRIGGERED", "NORMAL_CONDITIONS", "EVIDENCE_UNAVAILABLE")
            l_verdict = str(leader.get("verdict", "")).strip().upper()
            if l_verdict not in valid_verdicts:
                return False

            mine = leader_fn()
            m_verdict = str(mine.get("verdict", "")).strip().upper()

            # DISCRETE EQUIVALENCE: 100% agreement on exact disaster verdict
            return l_verdict == m_verdict

        adjudication_res = gl.vm.run_nondet(leader_fn, validator_fn)
        if isinstance(adjudication_res, dict):
            final_res = adjudication_res
        else:
            final_res = self._parse_llm_json(str(adjudication_res))

        verdict = str(final_res.get("verdict", "EVIDENCE_UNAVAILABLE")).strip().upper()
        valid_verdicts = ("TOTAL_LOSS_TRIGGERED", "PARTIAL_LOSS_TRIGGERED", "NORMAL_CONDITIONS", "EVIDENCE_UNAVAILABLE")
        if verdict not in valid_verdicts:
            verdict = "EVIDENCE_UNAVAILABLE"

        reason = str(final_res.get("reason", "Consensus concluded."))

        if verdict == "EVIDENCE_UNAVAILABLE":
            # Explicit Non-Settling Failure Path:
            # Weather observation evidence was unavailable, blank, 404, or unparseable.
            # DO NOT settle the policy. DO NOT transfer any funds to the insurer.
            # Preserve policy in ACTIVE status so it can be safely retried.
            policy.verdict = "EVIDENCE_UNAVAILABLE"
            policy.reason = f"Adjudication non-settling: {reason}. Policy and funds preserved for safe retry."
            self.policies[policy_id] = policy
            return

        policy.status = "SETTLED"
        policy.verdict = verdict
        policy.reason = reason
        policy.resolved_at = now_ts if now_ts > bigint(0) else self.policy_count

        total_funds = policy.coverage_amount + policy.premium_paid

        if verdict == "TOTAL_LOSS_TRIGGERED":
            # Catastrophic loss: Total coverage + premium refunded to farmer
            policy.farmer_payout = total_funds
            policy.insurer_payout = bigint(0)
            self.policies[policy_id] = policy
            _safe_transfer(policy.farmer, total_funds)

        elif verdict == "PARTIAL_LOSS_TRIGGERED":
            # 50% coverage to farmer; remaining to insurer
            half_cov = policy.coverage_amount // bigint(2)
            policy.farmer_payout = half_cov + policy.premium_paid
            policy.insurer_payout = policy.coverage_amount - half_cov
            self.policies[policy_id] = policy
            _safe_transfer(policy.farmer, policy.farmer_payout)
            _safe_transfer(policy.insurer, policy.insurer_payout)

        else:
            # Normal conditions: All coverage returned to insurer + insurer earns farmer's premium
            policy.farmer_payout = bigint(0)
            policy.insurer_payout = total_funds
            self.policies[policy_id] = policy
            _safe_transfer(policy.insurer, total_funds)

    @gl.public.write
    def cancel_unactivated_policy(self, policy_id: str) -> None:
        """
        Safe Insurer Recovery Path:
        If farmer never pays premium within grace period, insurer can cancel and reclaim coverage funds.
        """
        if policy_id not in self.policies:
            raise gl.UserError("Policy not found.")

        policy = self.policies[policy_id]
        if _addr_str(_get_sender()) != _addr_str(policy.insurer):
            raise gl.UserError("Only insurer can cancel unactivated policy.")

        if policy.status != "ACTIVE":
            raise gl.UserError("Policy is not in ACTIVE state.")

        if policy.premium_paid > bigint(0):
            raise gl.UserError("Cannot cancel policy once farmer has paid premium.")

        cov_amt = policy.coverage_amount
        policy.status = "CANCELLED"
        policy.verdict = "NORMAL_CONDITIONS"
        policy.reason = "Policy cancelled by insurer before farmer premium activation."
        now_ts = self._get_current_timestamp()
        policy.resolved_at = now_ts if now_ts > bigint(0) else self.policy_count
        self.policies[policy_id] = policy

        if cov_amt > bigint(0):
            _safe_transfer(policy.insurer, cov_amt)

    @gl.public.view
    def get_policy(self, policy_id: str) -> str:
        """Retrieve details of a crop insurance policy as a JSON string."""
        if policy_id not in self.policies:
            raise gl.UserError("Policy not found.")
        p = self.policies[policy_id]
        return json.dumps({
            "policy_id": p.policy_id,
            "farmer": _addr_str(p.farmer),
            "insurer": _addr_str(p.insurer),
            "risk_type": p.risk_type,
            "station_id": p.station_id,
            "trigger_threshold": p.trigger_threshold,
            "weather_data_url": p.weather_data_url,
            "premium_paid": str(p.premium_paid),
            "coverage_amount": str(p.coverage_amount),
            "status": p.status,
            "verdict": p.verdict,
            "farmer_payout": str(p.farmer_payout),
            "insurer_payout": str(p.insurer_payout),
            "reason": p.reason,
            "policy_start": str(p.policy_start),
            "policy_end": str(p.policy_end),
            "created_at": str(p.created_at),
            "resolved_at": str(p.resolved_at)
        })

    @gl.public.view
    def get_current_time(self) -> int:
        """Retrieve current contract execution timestamp."""
        return int(str(self._get_current_timestamp()))

    @gl.public.view
    def get_policy_count(self) -> int:
        return int(self.policy_count)

    @gl.public.view
    def get_owner(self) -> str:
        return _addr_str(self.owner)
