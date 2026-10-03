# F1 25 and 2026 Season Pack packet audit

Checked against EA's [official UDP specifications](https://forums.ea.com/blog/f1-games-game-info-hub-en/ea-sports%E2%84%A2-f1%C2%AE25-2026-season-pack-udp-specification/12187347), including the Season 8 PDF version 1.2, on 2026-10-03.

The app selects the byte layout using the received `packetFormat`, independently of the detected season. The legacy layout has 22 car slots; the 2026 layout has 24. `gameYear=25` can accompany 2026 packets and must not select the legacy byte layout.

| Packet | F1 25 record size | 2026 record size | Fields checked |
| --- | ---: | ---: | --- |
| 0 Motion | 60 | 54 | Position; longitudinal G is float at offset 40 in 2025, signed int16 / 1000 at offset 38 in 2026 |
| 1 Session | Single packet | Single packet | Formula at offset 8; track, session type, pause state, mode, persistent link identifiers |
| 2 Lap Data | 57 | 57 | Current/last time, distance at 20, lap number at 33, pit status at 34, invalid at 37 |
| 4 Participants | 57 | 60 | Active count; team ID is uint8 at 3 in 2025, uint16 at 5 in 2026 |
| 5 Car Setups | 50 | 50 | Player setup, including tyre pressures in RL, RR, FL, FR order |
| 6 Car Telemetry | 60 | 59 | Speed, throttle, brake, DRS; the engine-temperature field changes width |
| 7 Car Status | 55 | 59 | Fuel at 5/9/13, compounds at 25/26, tyre age at 27, MGU-K power at 33, stored energy at 37, deploy mode at 41 |
| 10 Car Damage | 46 | 46 | Four tyre-wear floats; stride includes tyre blisters |
| 13 Motion Ex | 273-byte packet | 273-byte packet | Wheel speeds at 48 and slip ratios at 64; player only |
| 16 Car Telemetry 2 | Not in original F1 25 | 10 | Active aero, Overtake availability/activity/distances and regulations |

Record offsets are relative to the car record; Session and Motion Ex offsets are relative to the payload after the 29-byte header. Other packet types are not consumed by the app's lap analysis.

## Automatic identification

- A 2026 packet-format header or game year 26 identifies the Season Pack immediately.
- Under the selectable legacy UDP format, Session formula 13, 2026 participant team IDs, the Madrid track, or a valid Car Telemetry 2 packet identifies 2026 content. Confirmed 2026 evidence survives subsequent common legacy headers within the session.
- Session formula 0 or original F1 participant team IDs 0..9 identify modern F1 25 content when the header and other evidence do not identify 2026. An explicit non-modern formula class prevents the original F1 grid signal from confirming F1 25. The Season 8 2026 F2 team IDs 489..499 also identify 2026 under legacy UDP.
- Controls alone under a 2025/25 header do not distinguish the editions. The app shows that it is detecting the edition until identifying data arrives. No manual selector is required.
- A new session UID, persistent session link, track or formula clears previous identification and car values. Identification arriving mid-lap updates the lap's metadata before saving.

Dedicated packet 16 fields take precedence over the older DRS/deploy fields. Deploy mode 3 means Boost in the 2026 wire schema and Overtake in the legacy schema; availability alone is never counted as activity.

## Validation

`tests/test_udp_packet_audit.py` replays both schemas offline, including their first and last car slots, distinct values for all fields above, malformed/truncated data, nonfinite floats, late identification, and transitions back to F1 25. It does not bind UDP 20777 or write synthetic laps into real recordings. The remaining telemetry/recorder tests verify saved motion samples and late edition metadata.

These checks verify decoding against published layouts. A new live driving session is still needed to verify the game's actual stream and populated map/acceleration data end to end. Existing recordings with zero motion values cannot recover their missing racing line.
