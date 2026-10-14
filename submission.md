# Portal Submission Draft — InsuranceWeatherCropX

**Portal Track:** Builder  
**Contribution Type:** Intelligent Contracts  
**Network:** studionet (Chain ID: 61999)  
**Contract Address:** `0x7315b8c5F0DC2f1edD893a19e620376dB0a43140`  
**Evidence URL 1:** `https://github.com/tuannguyen1995/insurance-weather-crop-x`  
**Evidence URL 2:** `https://explorer-studio.genlayer.com/address/0x7315b8c5F0DC2f1edD893a19e620376dB0a43140`  

---

### Title
```
InsuranceWeatherCropX — Parametric Extreme Weather Drought & Flood Insurance Protocol
```

### Notes / Description (<1000 characters)
```
InsuranceWeatherCropX is an autonomous parametric agricultural insurance protocol on GenLayer protecting farmers and cooperatives against extreme droughts and floods without manual loss adjusters.

Underwriters lock coverage in escrow and farmers pay premiums bound to regional certified weather stations and parametric trigger thresholds. Upon season completion, GenLayer validators scrape official meteorological observation data (Open-Meteo, NOAA, Weather.gov, ECMWF) directly on-chain via gl.nondet.web.render and evaluate conditions through an autonomous LLM validator jury.

Settlement enforces 100% discrete consensus: TOTAL_LOSS_TRIGGERED (100% coverage + premium to farmer), PARTIAL_LOSS_TRIGGERED (50% coverage split + premium to farmer), and NORMAL_CONDITIONS (coverage + earned premium to insurer). Canonical domain whitelisting, station ID binding, and safe cancellation recovery ensure capital is never trapped. 12/12 unit tests passed. Deployed on studionet: 0x7315b8c5F0DC2f1edD893a19e620376dB0a43140.
```
