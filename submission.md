# Portal Submission Draft — InsuranceWeatherCropX

**Portal Track:** Builder  
**Contribution Type:** Intelligent Contracts  
**Network:** studionet (Chain ID: 61999)  
**Contract Address:** `0xb53d1193d3cd1b7B9027ACf704B1eD9307f6F86A`  
**Evidence URL 1:** `https://github.com/tuannguyen1995/insurance-weather-crop-x`  
**Evidence URL 2:** `https://explorer-studio.genlayer.com/address/0xb53d1193d3cd1b7B9027ACf704B1eD9307f6F86A`  

---

### Title
```
InsuranceWeatherCropX — Parametric Extreme Weather Drought & Flood Insurance Protocol
```

### Notes / Description (<1000 characters)
```
InsuranceWeatherCropX is an autonomous parametric agricultural insurance protocol on GenLayer protecting farmers from severe droughts and floods without manual adjusters.

Underwriters lock coverage in escrow and farmers pay premiums bound to weather stations. Validators scrape official meteorological APIs (NOAA, Open-Meteo, ECMWF) on-chain via gl.nondet.web.render with 100% discrete LLM consensus (TOTAL_LOSS_TRIGGERED, PARTIAL_LOSS_TRIGGERED, NORMAL_CONDITIONS).

Failure Path Update: When weather data is offline, blank, 404, or unparseable, consensus classifies as EVIDENCE_UNAVAILABLE—preserving policy in ACTIVE state with 0 disbursement so funds remain safe for retry. Parties can also call update_weather_data_url() for verified fallback stations. 13/13 gltest unit tests passed.

Deployed on Studionet: 0xb53d1193d3cd1b7B9027ACf704B1eD9307f6F86A
GitHub: https://github.com/tuannguyen1995/insurance-weather-crop-x
```

### Steward Response (Joaquin)
```
Dear Joaquin,

We have updated the contract adjudication failure path as requested:
1. When weather observation data is unavailable, blank, 404/error, or unparseable, the consensus jury now yields an explicit non-settling verdict `EVIDENCE_UNAVAILABLE`.
2. In this failure path, the policy remains `ACTIVE`, and 0 funds are transferred to the insurer or farmer, preserving 100% of escrowed capital for a safe retry.
3. Added `update_weather_data_url()` allowing authorized parties to migrate to an alternative whitelisted meteorological endpoint if an existing station is decommissioned.
4. Deployed directly to Studionet (0xb53d1193d3cd1b7B9027ACf704B1eD9307f6F86A) with identical bytecode and sender-resolution logic matching the latest GitHub commit. All 13 unit tests pass.
```
