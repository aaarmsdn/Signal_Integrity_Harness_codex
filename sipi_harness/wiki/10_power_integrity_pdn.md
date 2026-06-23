---
graph: false
kind: hub_page
id: wiki_power_integrity_pdn
topic: power_integrity
summary: "Power integrity strategy organizes PDN impedance, IR drop, SSN, decoupling, rail noise, and transient response into a traceable design graph."
concepts:
  - Power Integrity
  - PDN
  - Target Impedance
  - IR Drop
  - SSN
  - Ground Bounce
  - Decoupling
  - Rail Noise
  - Transient Response
  - Voltage Margin
claims:
  - "Power integrity starts from rail tolerance, current demand, and load-step assumptions."
  - "Target impedance links load-step current to allowed rail noise."
  - "IR drop consumes static voltage margin before AC ripple and SSN are considered."
  - "Decoupling effectiveness is dominated by loop inductance, mounting geometry, via placement, and capacitor model quality."
relationships:
  - "Power Integrity|contains|PDN"
  - "PDN|is constrained by|Target Impedance"
  - "PDN|is checked by|Transient Response"
  - "IR Drop|consumes|Voltage Margin"
  - "SSN|causes|Ground Bounce"
  - "Ground Bounce|appears as|Rail Noise"
  - "Decoupling|reduces|Rail Noise"
  - "Decoupling|damps|PDN"
---

# Power Integrity and PDN

Power integrity asks whether a rail remains inside its voltage budget under DC
load, dynamic load steps, simultaneous switching, and package/board current
return effects.

## Category Map

```text
Power Integrity
  -> PDN
     -> Target Impedance
     -> Transient Response
     -> Decoupling
  -> IR Drop
     -> Voltage Margin
  -> SSN
     -> Ground Bounce
     -> Rail Noise
```

## Strategy Checklist

1. Define rail tolerance, nominal voltage, DC current, transient current step,
   and edge/load profile.
2. Compute or set target impedance from allowed noise and load step.
3. Allocate voltage margin across IR drop, ripple, SSN, and measurement/model
   uncertainty.
4. Place decoupling by loop inductance and current path, not only capacitance
   value.
5. Simulate impedance and transient response at the relevant pins/loads.
6. Iterate plane geometry, via count, capacitor selection, package current
   path, and VRM model until the rail budget closes.

## Typed Cards

PI-specific typed cards should be added under `design_rules/`, `stackups/`, and
`validation/` as source-backed rules are ingested. This hub remains an overview
only.
