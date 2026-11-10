# Mumbai PM2.5 forecasting entry

Reproduce from this folder with `python pipeline.py` (Python 3.14.6; this run took 39.43 seconds). The pipeline reads only provided challenge files, uses fixed seed 20261110, and requires `numpy==2.5.4` for its optional weighted Ridge attempt; all other imports are from the standard library.

## Submitted files and selection

Select `Submission/01_Final_Submissions/submission_primary.csv` (B0) and `Submission/01_Final_Submissions/submission_hedged.csv` on Zindi. The fault-excluded point leader was blend_w0.45: RMSE 17.4051 vs B0 17.4101 (difference -0.0050; 95% origin-block CI [-0.0940, 0.1203]). The interval includes zero, so B0 remains primary. The hedged file applies the c=2 robust anchor to each station and an extra 20% shrink toward the 14-day profile for 11611. Weighted Ridge tested but not adopted because it did not satisfy both evidence gates.

The public score is uninformative about forecast quality because 1,284 Test rows are observed Train values copied into the submissions. Private rows are selected by target date (11 Nov 01:00 through 13 Nov 00:00 IST), not by stale `scoring_block` labels.

## Public intervals

Date-window CSV extracts are saved under `Submission/02_Public_Intervals/` in chronological order, with counts and observed-versus-filled rows in `00_interval_manifest.csv`. They are subsets of the primary output and retain Test.csv row order.

## Backtest evidence

Daily 09:00 IST origins from 2025-04-01 through 2026-11-07; direct horizons 16–63. Six methods use the same common rows (n=86840 overall): B0, last24, profile3, profile7, profile14-median, and same-hour-yesterday. Spike origin means any station's last-24-hour mean exceeds 80. Fault-excluded removes the documented station 3409511 window and any target invalidated by the isolation rule.

| Method | Targets | Group | n | RMSE | MAE | ΔRMSE vs B0 | 95% CI |
|---|---|---|---:|---:|---:|---:|---:|
| B0 | all | overall | 86840 | 19.9505 | 10.2275 | 0.0000 | [0.0000, 0.0000] |
| last24 | all | overall | 86840 | 21.2161 | 10.9576 | 1.2656 | [0.4445, 2.4184] |
| profile3 | all | overall | 86840 | 21.8315 | 11.0770 | 1.8810 | [1.2220, 2.6391] |
| profile7 | all | overall | 86840 | 21.0619 | 11.0235 | 1.1113 | [0.6820, 1.5666] |
| profile14median | all | overall | 86840 | 21.7680 | 11.7403 | 1.8175 | [1.2014, 2.4218] |
| same_hour_yesterday | all | overall | 86840 | 21.2309 | 10.9363 | 1.2804 | [0.8684, 1.7541] |
| B0 | all | calm_origins | 80904 | 17.0882 | 9.2865 | 0.0000 | [0.0000, 0.0000] |
| last24 | all | calm_origins | 80904 | 17.5731 | 9.7411 | 0.4848 | [-0.0320, 0.9646] |
| profile3 | all | calm_origins | 80904 | 18.2376 | 9.9821 | 1.1494 | [0.6511, 1.7609] |
| profile7 | all | calm_origins | 80904 | 18.2967 | 10.0874 | 1.2085 | [0.8118, 1.6828] |
| profile14median | all | calm_origins | 80904 | 18.7135 | 10.6325 | 1.6252 | [1.1391, 2.1537] |
| same_hour_yesterday | all | calm_origins | 80904 | 18.0806 | 9.9657 | 0.9924 | [0.6782, 1.3048] |
| B0 | all | spike_origins | 5936 | 42.9295 | 23.0526 | 0.0000 | [0.0000, 0.0000] |
| last24 | all | spike_origins | 5936 | 48.7454 | 27.5380 | 5.8159 | [1.4590, 12.3090] |
| profile3 | all | spike_origins | 5936 | 49.3896 | 25.9994 | 6.4601 | [2.9335, 10.2494] |
| profile7 | all | spike_origins | 5936 | 43.8966 | 23.7817 | 0.9672 | [-1.0437, 2.2720] |
| profile14median | all | spike_origins | 5936 | 46.4666 | 26.8384 | 3.5371 | [0.2107, 6.2285] |
| same_hour_yesterday | all | spike_origins | 5936 | 46.2456 | 24.1643 | 3.3161 | [1.1904, 5.6980] |
| B0 | all | 11611 | 22540 | 21.7947 | 11.3176 | 0.0000 | [0.0000, 0.0000] |
| last24 | all | 11611 | 22540 | 23.9068 | 12.3260 | 2.1120 | [0.2739, 4.9102] |
| profile3 | all | 11611 | 22540 | 23.6126 | 12.2111 | 1.8179 | [0.7725, 2.9898] |
| profile7 | all | 11611 | 22540 | 22.7730 | 11.9738 | 0.9783 | [0.0727, 1.7401] |
| profile14median | all | 11611 | 22540 | 23.3360 | 12.5435 | 1.5413 | [0.5765, 2.4459] |
| same_hour_yesterday | all | 11611 | 22540 | 23.1172 | 11.9423 | 1.3225 | [0.5365, 2.2775] |
| B0 | all | 11606 | 22103 | 12.9664 | 8.9466 | 0.0000 | [0.0000, 0.0000] |
| last24 | all | 11606 | 22103 | 13.6537 | 9.3578 | 0.6872 | [0.2066, 1.2072] |
| profile3 | all | 11606 | 22103 | 14.3656 | 9.8855 | 1.3992 | [0.9869, 1.8968] |
| profile7 | all | 11606 | 22103 | 13.9405 | 9.6895 | 0.9741 | [0.6441, 1.3059] |
| profile14median | all | 11606 | 22103 | 14.7688 | 10.4703 | 1.8023 | [1.2801, 2.2940] |
| same_hour_yesterday | all | 11606 | 22103 | 13.8656 | 9.6678 | 0.8992 | [0.6558, 1.1759] |
| B0 | all | 3409510 | 20699 | 16.0590 | 9.0484 | 0.0000 | [0.0000, 0.0000] |
| last24 | all | 3409510 | 20699 | 17.1193 | 9.6698 | 1.0604 | [0.0979, 2.2246] |
| profile3 | all | 3409510 | 20699 | 17.6646 | 9.7667 | 1.6057 | [0.6261, 2.8484] |
| profile7 | all | 3409510 | 20699 | 17.1974 | 9.7972 | 1.1385 | [0.6171, 1.6045] |
| profile14median | all | 3409510 | 20699 | 18.1785 | 10.6848 | 2.1195 | [1.3595, 2.9135] |
| same_hour_yesterday | all | 3409510 | 20699 | 17.1537 | 9.6734 | 1.0948 | [0.7548, 1.4403] |
| B0 | all | 3409511 | 21498 | 26.2411 | 11.5366 | 0.0000 | [0.0000, 0.0000] |
| last24 | all | 3409511 | 21498 | 27.2977 | 12.4077 | 1.0567 | [0.2030, 1.9915] |
| profile3 | all | 3409511 | 21498 | 28.7761 | 12.3744 | 2.5350 | [1.2100, 4.2661] |
| profile7 | all | 3409511 | 21498 | 27.6332 | 12.5792 | 1.3921 | [0.9044, 1.9298] |
| profile14median | all | 3409511 | 21498 | 28.2963 | 13.2200 | 2.0553 | [1.2837, 2.7687] |
| same_hour_yesterday | all | 3409511 | 21498 | 27.9195 | 12.4017 | 1.6784 | [0.9483, 2.4405] |
| B0 | fault_excluded | overall | 84499 | 17.4101 | 9.5618 | 0.0000 | [0.0000, 0.0000] |
| last24 | fault_excluded | overall | 84499 | 18.6800 | 10.2579 | 1.2699 | [0.4069, 2.5671] |
| profile3 | fault_excluded | overall | 84499 | 18.7991 | 10.3231 | 1.3890 | [0.8120, 2.0666] |
| profile7 | fault_excluded | overall | 84499 | 18.3531 | 10.2781 | 0.9430 | [0.5265, 1.3423] |
| profile14median | fault_excluded | overall | 84499 | 18.9424 | 10.9278 | 1.5323 | [1.0092, 2.0606] |
| same_hour_yesterday | fault_excluded | overall | 84499 | 18.4231 | 10.2011 | 1.0130 | [0.6808, 1.4189] |
| B0 | fault_excluded | calm_origins | 79711 | 15.8412 | 8.9510 | 0.0000 | [0.0000, 0.0000] |
| last24 | fault_excluded | calm_origins | 79711 | 16.4050 | 9.4577 | 0.5638 | [0.1340, 0.9897] |
| profile3 | fault_excluded | calm_origins | 79711 | 16.9163 | 9.6328 | 1.0752 | [0.6312, 1.6625] |
| profile7 | fault_excluded | calm_origins | 79711 | 16.9206 | 9.6869 | 1.0794 | [0.7524, 1.4435] |
| profile14median | fault_excluded | calm_origins | 79711 | 17.2231 | 10.1765 | 1.3820 | [0.9276, 1.8817] |
| same_hour_yesterday | fault_excluded | calm_origins | 79711 | 16.7474 | 9.5836 | 0.9062 | [0.6671, 1.1756] |
| B0 | fault_excluded | spike_origins | 4788 | 34.2288 | 19.7299 | 0.0000 | [0.0000, 0.0000] |
| last24 | fault_excluded | spike_origins | 4788 | 40.9608 | 23.5806 | 6.7319 | [0.5815, 15.2649] |
| profile3 | fault_excluded | spike_origins | 4788 | 38.3782 | 21.8144 | 4.1494 | [1.2476, 8.7128] |
| profile7 | fault_excluded | spike_origins | 4788 | 34.3230 | 20.1207 | 0.0942 | [-2.7414, 2.0216] |
| profile14median | fault_excluded | spike_origins | 4788 | 37.3357 | 23.4360 | 3.1068 | [-0.4675, 6.1617] |
| same_hour_yesterday | fault_excluded | spike_origins | 4788 | 36.3393 | 20.4806 | 2.1105 | [-0.2424, 5.1609] |
| B0 | fault_excluded | 11611 | 22540 | 21.7947 | 11.3176 | 0.0000 | [0.0000, 0.0000] |
| last24 | fault_excluded | 11611 | 22540 | 23.9068 | 12.3260 | 2.1120 | [0.2836, 4.8115] |
| profile3 | fault_excluded | 11611 | 22540 | 23.6126 | 12.2111 | 1.8179 | [0.7690, 3.0323] |
| profile7 | fault_excluded | 11611 | 22540 | 22.7730 | 11.9738 | 0.9783 | [0.1189, 1.7294] |
| profile14median | fault_excluded | 11611 | 22540 | 23.3360 | 12.5435 | 1.5413 | [0.5129, 2.4083] |
| same_hour_yesterday | fault_excluded | 11611 | 22540 | 23.1172 | 11.9423 | 1.3225 | [0.4953, 2.3880] |
| B0 | fault_excluded | 11606 | 22103 | 12.9664 | 8.9466 | 0.0000 | [0.0000, 0.0000] |
| last24 | fault_excluded | 11606 | 22103 | 13.6537 | 9.3578 | 0.6872 | [0.1497, 1.1835] |
| profile3 | fault_excluded | 11606 | 22103 | 14.3656 | 9.8855 | 1.3992 | [0.9849, 1.8603] |
| profile7 | fault_excluded | 11606 | 22103 | 13.9405 | 9.6895 | 0.9741 | [0.6584, 1.3172] |
| profile14median | fault_excluded | 11606 | 22103 | 14.7688 | 10.4703 | 1.8023 | [1.2346, 2.3982] |
| same_hour_yesterday | fault_excluded | 11606 | 22103 | 13.8656 | 9.6678 | 0.8992 | [0.6278, 1.1778] |
| B0 | fault_excluded | 3409510 | 20699 | 16.0590 | 9.0484 | 0.0000 | [0.0000, 0.0000] |
| last24 | fault_excluded | 3409510 | 20699 | 17.1193 | 9.6698 | 1.0604 | [0.1788, 2.2135] |
| profile3 | fault_excluded | 3409510 | 20699 | 17.6646 | 9.7667 | 1.6057 | [0.6612, 2.7757] |
| profile7 | fault_excluded | 3409510 | 20699 | 17.1974 | 9.7972 | 1.1385 | [0.7095, 1.6078] |
| profile14median | fault_excluded | 3409510 | 20699 | 18.1785 | 10.6848 | 2.1195 | [1.3899, 2.8974] |
| same_hour_yesterday | fault_excluded | 3409510 | 20699 | 17.1537 | 9.6734 | 1.0948 | [0.7699, 1.4318] |
| B0 | fault_excluded | 3409511 | 19157 | 17.4773 | 8.7605 | 0.0000 | [0.0000, 0.0000] |
| last24 | fault_excluded | 3409511 | 19157 | 18.3010 | 9.4987 | 0.8236 | [0.3389, 1.4101] |
| profile3 | fault_excluded | 3409511 | 19157 | 18.0983 | 9.2076 | 0.6210 | [0.1931, 1.1603] |
| profile7 | fault_excluded | 3409511 | 19157 | 18.2144 | 9.4818 | 0.7370 | [0.4776, 1.0896] |
| profile14median | fault_excluded | 3409511 | 19157 | 18.2546 | 9.8173 | 0.7772 | [0.3106, 1.2836] |
| same_hour_yesterday | fault_excluded | 3409511 | 19157 | 18.1260 | 9.3378 | 0.6487 | [0.4210, 0.9788] |

The same table is saved as `backtest_evidence.csv`; `backtest_summary.csv` and `backtest_bootstrap.csv` provide the component summaries. The 49 MB row-level `backtest_rows.csv` is generated by the pipeline but is omitted from this repository.

## Data handling and limitations

The competition-provided `Train.csv`, `Test.csv`, and `SampleSubmission.csv` files are not included. Download them from Zindi into this folder before running the pipeline.

Forecast features use observations at or before each origin. Values above 1,000 are invalidated; values above 500 are invalidated when the median of available simultaneous peer readings is below 150. Station 11611 has stayed about 3× the median of the other stations for eight consecutive hours (roughly 190–260 µg/m³); there is no historical precedent, so local source vs. sensor fault remains unknown. Diwali decay remains uncertain (roughly 0.5–1.3× the recent level); no decay is hard-coded. Fault-rule thresholds may remove genuine station-specific extremes. There is a 243-hour no-station gap in January 2026.

The Zindi rule claims in the task were not independently verified during this run. Historical archives are not used as features and source station IDs are not merged.

## Optional ML result

Walk-forward weighted Ridge used 86840 scored rows and 23 origin-anchored features. Fault-excluded RMSE: Ridge 19.6461, B0 17.4101; difference 2.2360, 95% origin-bootstrap CI [1.4714, 2.9842]. All-target RMSE: Ridge 22.6458, B0 19.9505. Adoption requires CI high < 0 and all-target RMSE at most B0 + 1; result: NOT ADOPTED. 

