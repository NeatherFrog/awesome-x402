# Futures session research against 8% monthly

Adaptive retrospective study; existing prices were inspected before. No real trades or qualified live strategy.

Protocol SHA256: `6a44ec48585a5a88190cb60936c828073cc9e441b7d885fa1ebd32eb82359a04`. 48 frozen economic rules×3 predeclaredTRAINrisk levels=144portfolio variants/288market hypotheses.
Regular futures hourly data cannot represent09:30RTH opening range: the first full interval is10–11NY. Halfdays use the known09:30anchor; daily flatten15:00normal/12:30halfday.
VWAP is only an OHLC-volume proxy. 100k nominal balance is not margin; TRAINselects initially250/500/750dollars plannedrisk per market, fixedintegercontract cap10/asset, fixed fees and adverse ticks. No failed heldout return is rescaled.

Locked training candidate: `release_c4_e0.75_r1.5_t1__risk0.5`; selected eligible variant: `None`.

| Period | Net total | Geometric monthly | Double-cost monthly | Episodes | Adverse DD | Gate |
|---|---:|---:|---:|---:|---:|---|
|training|0.165%|0.055%|-0.008%|26|0.623%|fail|
|validation|not evaluated|—|—|—|—|no eligible training candidate|
|final|not evaluated|—|—|—|—|no eligible training candidate|

| Frozen variant | Train net | Train monthly | Double-cost monthly | Train episodes | Training gate |
|---|---:|---:|---:|---:|---|
|orb_h1_b0_r1.5_t0__risk0.5|-0.546%|-0.182%|-0.335%|63|fail|
|orb_h1_b0_r1.5_t0__risk1|-0.897%|-0.300%|-0.573%|92|fail|
|orb_h1_b0_r1.5_t0__risk1.5|-1.310%|-0.439%|-0.936%|93|fail|
|orb_h1_b0_r1.5_t1__risk0.5|-0.640%|-0.214%|-0.337%|47|fail|
|orb_h1_b0_r1.5_t1__risk1|-1.605%|-0.538%|-0.632%|69|fail|
|orb_h1_b0_r1.5_t1__risk1.5|-2.767%|-0.931%|-1.249%|70|fail|
|orb_h1_b0_r2.5_t0__risk0.5|-0.292%|-0.097%|-0.250%|63|fail|
|orb_h1_b0_r2.5_t0__risk1|-0.412%|-0.138%|-0.368%|92|fail|
|orb_h1_b0_r2.5_t0__risk1.5|-0.604%|-0.202%|-0.627%|93|fail|
|orb_h1_b0_r2.5_t1__risk0.5|-0.442%|-0.148%|-0.270%|47|fail|
|orb_h1_b0_r2.5_t1__risk1|-1.071%|-0.358%|-0.522%|69|fail|
|orb_h1_b0_r2.5_t1__risk1.5|-2.183%|-0.733%|-1.036%|70|fail|
|orb_h1_b0.1_r1.5_t0__risk0.5|-0.678%|-0.227%|-0.318%|56|fail|
|orb_h1_b0.1_r1.5_t0__risk1|-0.837%|-0.280%|-0.449%|85|fail|
|orb_h1_b0.1_r1.5_t0__risk1.5|-1.465%|-0.491%|-0.861%|86|fail|
|orb_h1_b0.1_r1.5_t1__risk0.5|-1.026%|-0.343%|-0.406%|42|fail|
|orb_h1_b0.1_r1.5_t1__risk1|-2.095%|-0.703%|-0.750%|65|fail|
|orb_h1_b0.1_r1.5_t1__risk1.5|-3.536%|-1.193%|-1.457%|66|fail|
|orb_h1_b0.1_r2.5_t0__risk0.5|-0.487%|-0.163%|-0.254%|56|fail|
|orb_h1_b0.1_r2.5_t0__risk1|-0.472%|-0.158%|-0.339%|85|fail|
|orb_h1_b0.1_r2.5_t0__risk1.5|-0.992%|-0.332%|-0.729%|86|fail|
|orb_h1_b0.1_r2.5_t1__risk0.5|-0.827%|-0.277%|-0.340%|42|fail|
|orb_h1_b0.1_r2.5_t1__risk1|-1.700%|-0.570%|-0.647%|65|fail|
|orb_h1_b0.1_r2.5_t1__risk1.5|-2.995%|-1.008%|-1.254%|66|fail|
|orb_h2_b0_r1.5_t0__risk0.5|-0.494%|-0.165%|-0.193%|33|fail|
|orb_h2_b0_r1.5_t0__risk1|-1.564%|-0.524%|-0.607%|49|fail|
|orb_h2_b0_r1.5_t0__risk1.5|-3.033%|-1.021%|-1.220%|55|fail|
|orb_h2_b0_r1.5_t1__risk0.5|-0.607%|-0.203%|-0.217%|26|fail|
|orb_h2_b0_r1.5_t1__risk1|-1.660%|-0.557%|-0.582%|38|fail|
|orb_h2_b0_r1.5_t1__risk1.5|-2.786%|-0.938%|-1.100%|42|fail|
|orb_h2_b0_r2.5_t0__risk0.5|-0.399%|-0.133%|-0.161%|33|fail|
|orb_h2_b0_r2.5_t0__risk1|-1.326%|-0.444%|-0.527%|49|fail|
|orb_h2_b0_r2.5_t0__risk1.5|-2.683%|-0.902%|-1.128%|55|fail|
|orb_h2_b0_r2.5_t1__risk0.5|-0.607%|-0.203%|-0.217%|26|fail|
|orb_h2_b0_r2.5_t1__risk1|-1.660%|-0.557%|-0.582%|38|fail|
|orb_h2_b0_r2.5_t1__risk1.5|-2.786%|-0.938%|-1.100%|42|fail|
|orb_h2_b0.1_r1.5_t0__risk0.5|-0.998%|-0.334%|-0.340%|28|fail|
|orb_h2_b0.1_r1.5_t0__risk1|-2.671%|-0.898%|-0.910%|43|fail|
|orb_h2_b0.1_r1.5_t0__risk1.5|-4.626%|-1.567%|-1.735%|49|fail|
|orb_h2_b0.1_r1.5_t1__risk0.5|-0.767%|-0.256%|-0.253%|22|fail|
|orb_h2_b0.1_r1.5_t1__risk1|-1.879%|-0.630%|-0.658%|33|fail|
|orb_h2_b0.1_r1.5_t1__risk1.5|-3.205%|-1.080%|-1.180%|37|fail|
|orb_h2_b0.1_r2.5_t0__risk0.5|-0.998%|-0.334%|-0.340%|28|fail|
|orb_h2_b0.1_r2.5_t0__risk1|-2.671%|-0.898%|-0.910%|43|fail|
|orb_h2_b0.1_r2.5_t0__risk1.5|-4.626%|-1.567%|-1.735%|49|fail|
|orb_h2_b0.1_r2.5_t1__risk0.5|-0.767%|-0.256%|-0.253%|22|fail|
|orb_h2_b0.1_r2.5_t1__risk1|-1.879%|-0.630%|-0.658%|33|fail|
|orb_h2_b0.1_r2.5_t1__risk1.5|-3.205%|-1.080%|-1.180%|37|fail|
|failure_h1_e0_midpoint_t0__risk0.5|-1.196%|-0.400%|-0.470%|57|fail|
|failure_h1_e0_midpoint_t0__risk1|-1.773%|-0.594%|-0.663%|58|fail|
|failure_h1_e0_midpoint_t0__risk1.5|-1.137%|-0.380%|-0.502%|58|fail|
|failure_h1_e0_midpoint_t1__risk0.5|-0.971%|-0.325%|-0.471%|37|fail|
|failure_h1_e0_midpoint_t1__risk1|-1.538%|-0.515%|-0.810%|37|fail|
|failure_h1_e0_midpoint_t1__risk1.5|-1.868%|-0.627%|-0.941%|37|fail|
|failure_h1_e0_vwap_proxy_t0__risk0.5|-0.685%|-0.229%|-0.232%|39|fail|
|failure_h1_e0_vwap_proxy_t0__risk1|-1.634%|-0.548%|-0.522%|39|fail|
|failure_h1_e0_vwap_proxy_t0__risk1.5|-1.828%|-0.613%|-0.608%|39|fail|
|failure_h1_e0_vwap_proxy_t1__risk0.5|-0.660%|-0.221%|-0.342%|28|fail|
|failure_h1_e0_vwap_proxy_t1__risk1|-1.337%|-0.448%|-0.668%|28|fail|
|failure_h1_e0_vwap_proxy_t1__risk1.5|-1.620%|-0.543%|-0.770%|28|fail|
|failure_h1_e0.25_midpoint_t0__risk0.5|-0.271%|-0.090%|-0.138%|27|fail|
|failure_h1_e0.25_midpoint_t0__risk1|-0.605%|-0.202%|-0.248%|28|fail|
|failure_h1_e0.25_midpoint_t0__risk1.5|-0.762%|-0.255%|-0.287%|28|fail|
|failure_h1_e0.25_midpoint_t1__risk0.5|-0.265%|-0.089%|-0.136%|16|fail|
|failure_h1_e0.25_midpoint_t1__risk1|-0.618%|-0.207%|-0.297%|16|fail|
|failure_h1_e0.25_midpoint_t1__risk1.5|-0.921%|-0.308%|-0.413%|16|fail|
|failure_h1_e0.25_vwap_proxy_t0__risk0.5|-0.347%|-0.116%|-0.156%|14|fail|
|failure_h1_e0.25_vwap_proxy_t0__risk1|-0.827%|-0.276%|-0.360%|14|fail|
|failure_h1_e0.25_vwap_proxy_t0__risk1.5|-1.040%|-0.348%|-0.432%|14|fail|
|failure_h1_e0.25_vwap_proxy_t1__risk0.5|-0.394%|-0.132%|-0.163%|11|fail|
|failure_h1_e0.25_vwap_proxy_t1__risk1|-0.945%|-0.316%|-0.378%|11|fail|
|failure_h1_e0.25_vwap_proxy_t1__risk1.5|-1.193%|-0.399%|-0.468%|11|fail|
|failure_h2_e0_midpoint_t0__risk0.5|-0.744%|-0.248%|-0.373%|48|fail|
|failure_h2_e0_midpoint_t0__risk1|-1.542%|-0.517%|-0.764%|49|fail|
|failure_h2_e0_midpoint_t0__risk1.5|-1.196%|-0.400%|-0.858%|49|fail|
|failure_h2_e0_midpoint_t1__risk0.5|0.114%|0.038%|-0.090%|35|fail|
|failure_h2_e0_midpoint_t1__risk1|-0.286%|-0.095%|-0.257%|35|fail|
|failure_h2_e0_midpoint_t1__risk1.5|0.250%|0.083%|-0.238%|35|fail|
|failure_h2_e0_vwap_proxy_t0__risk0.5|-0.285%|-0.095%|-0.226%|41|fail|
|failure_h2_e0_vwap_proxy_t0__risk1|-0.666%|-0.222%|-0.391%|41|fail|
|failure_h2_e0_vwap_proxy_t0__risk1.5|-0.270%|-0.090%|-0.415%|41|fail|
|failure_h2_e0_vwap_proxy_t1__risk0.5|-0.252%|-0.084%|-0.190%|30|fail|
|failure_h2_e0_vwap_proxy_t1__risk1|-0.810%|-0.271%|-0.403%|30|fail|
|failure_h2_e0_vwap_proxy_t1__risk1.5|-0.723%|-0.242%|-0.471%|30|fail|
|failure_h2_e0.25_midpoint_t0__risk0.5|-0.456%|-0.152%|-0.180%|14|fail|
|failure_h2_e0.25_midpoint_t0__risk1|-0.977%|-0.327%|-0.352%|15|fail|
|failure_h2_e0.25_midpoint_t0__risk1.5|-1.469%|-0.492%|-0.585%|15|fail|
|failure_h2_e0.25_midpoint_t1__risk0.5|-0.428%|-0.143%|-0.161%|10|fail|
|failure_h2_e0.25_midpoint_t1__risk1|-0.931%|-0.311%|-0.318%|10|fail|
|failure_h2_e0.25_midpoint_t1__risk1.5|-1.406%|-0.471%|-0.528%|10|fail|
|failure_h2_e0.25_vwap_proxy_t0__risk0.5|-0.470%|-0.157%|-0.183%|12|fail|
|failure_h2_e0.25_vwap_proxy_t0__risk1|-0.983%|-0.329%|-0.391%|12|fail|
|failure_h2_e0.25_vwap_proxy_t0__risk1.5|-1.582%|-0.530%|-0.618%|12|fail|
|failure_h2_e0.25_vwap_proxy_t1__risk0.5|-0.443%|-0.148%|-0.166%|9|fail|
|failure_h2_e0.25_vwap_proxy_t1__risk1|-1.023%|-0.342%|-0.349%|9|fail|
|failure_h2_e0.25_vwap_proxy_t1__risk1.5|-1.482%|-0.496%|-0.553%|9|fail|
|release_c4_e0.75_r1.5_t0__risk0.5|-0.215%|-0.072%|-0.143%|31|fail|
|release_c4_e0.75_r1.5_t0__risk1|-0.806%|-0.269%|-0.384%|39|fail|
|release_c4_e0.75_r1.5_t0__risk1.5|-1.376%|-0.461%|-0.605%|41|fail|
|release_c4_e0.75_r1.5_t1__risk0.5|0.165%|0.055%|-0.008%|26|fail|
|release_c4_e0.75_r1.5_t1__risk1|0.002%|0.001%|-0.091%|31|fail|
|release_c4_e0.75_r1.5_t1__risk1.5|-0.630%|-0.210%|-0.415%|33|fail|
|release_c4_e0.75_r2.5_t0__risk0.5|-0.402%|-0.134%|-0.205%|31|fail|
|release_c4_e0.75_r2.5_t0__risk1|-1.181%|-0.395%|-0.483%|39|fail|
|release_c4_e0.75_r2.5_t0__risk1.5|-1.964%|-0.659%|-0.827%|41|fail|
|release_c4_e0.75_r2.5_t1__risk0.5|-0.023%|-0.008%|-0.070%|26|fail|
|release_c4_e0.75_r2.5_t1__risk1|-0.373%|-0.124%|-0.190%|31|fail|
|release_c4_e0.75_r2.5_t1__risk1.5|-1.286%|-0.431%|-0.577%|33|fail|
|release_c4_e1.25_r1.5_t0__risk0.5|-0.145%|-0.048%|-0.037%|6|fail|
|release_c4_e1.25_r1.5_t0__risk1|-0.431%|-0.144%|-0.153%|13|fail|
|release_c4_e1.25_r1.5_t0__risk1.5|-1.439%|-0.482%|-0.513%|16|fail|
|release_c4_e1.25_r1.5_t1__risk0.5|-0.232%|-0.077%|-0.065%|5|fail|
|release_c4_e1.25_r1.5_t1__risk1|-0.565%|-0.189%|-0.191%|9|fail|
|release_c4_e1.25_r1.5_t1__risk1.5|-1.439%|-0.482%|-0.497%|11|fail|
|release_c4_e1.25_r2.5_t0__risk0.5|-0.145%|-0.048%|-0.037%|6|fail|
|release_c4_e1.25_r2.5_t0__risk1|-0.431%|-0.144%|-0.153%|13|fail|
|release_c4_e1.25_r2.5_t0__risk1.5|-1.439%|-0.482%|-0.513%|16|fail|
|release_c4_e1.25_r2.5_t1__risk0.5|-0.232%|-0.077%|-0.065%|5|fail|
|release_c4_e1.25_r2.5_t1__risk1|-0.565%|-0.189%|-0.191%|9|fail|
|release_c4_e1.25_r2.5_t1__risk1.5|-1.439%|-0.482%|-0.497%|11|fail|
|release_c8_e0.75_r1.5_t0__risk0.5|-0.408%|-0.136%|-0.195%|23|fail|
|release_c8_e0.75_r1.5_t0__risk1|-0.969%|-0.324%|-0.425%|27|fail|
|release_c8_e0.75_r1.5_t0__risk1.5|-1.286%|-0.431%|-0.549%|28|fail|
|release_c8_e0.75_r1.5_t1__risk0.5|0.055%|0.018%|-0.034%|21|fail|
|release_c8_e0.75_r1.5_t1__risk1|-0.042%|-0.014%|-0.105%|25|fail|
|release_c8_e0.75_r1.5_t1__risk1.5|-0.642%|-0.215%|-0.070%|27|fail|
|release_c8_e0.75_r2.5_t0__risk0.5|-0.596%|-0.199%|-0.258%|23|fail|
|release_c8_e0.75_r2.5_t0__risk1|-1.344%|-0.450%|-0.525%|27|fail|
|release_c8_e0.75_r2.5_t0__risk1.5|-1.869%|-0.627%|-0.743%|28|fail|
|release_c8_e0.75_r2.5_t1__risk0.5|-0.132%|-0.044%|-0.100%|21|fail|
|release_c8_e0.75_r2.5_t1__risk1|-0.417%|-0.139%|-0.234%|25|fail|
|release_c8_e0.75_r2.5_t1__risk1.5|-1.225%|-0.410%|-0.292%|27|fail|
|release_c8_e1.25_r1.5_t0__risk0.5|-0.232%|-0.077%|-0.065%|5|fail|
|release_c8_e1.25_r1.5_t0__risk1|-0.565%|-0.189%|-0.191%|9|fail|
|release_c8_e1.25_r1.5_t0__risk1.5|-1.439%|-0.482%|-0.497%|11|fail|
|release_c8_e1.25_r1.5_t1__risk0.5|-0.232%|-0.077%|-0.065%|5|fail|
|release_c8_e1.25_r1.5_t1__risk1|-0.565%|-0.189%|-0.191%|9|fail|
|release_c8_e1.25_r1.5_t1__risk1.5|-1.439%|-0.482%|-0.497%|11|fail|
|release_c8_e1.25_r2.5_t0__risk0.5|-0.232%|-0.077%|-0.065%|5|fail|
|release_c8_e1.25_r2.5_t0__risk1|-0.565%|-0.189%|-0.191%|9|fail|
|release_c8_e1.25_r2.5_t0__risk1.5|-1.439%|-0.482%|-0.497%|11|fail|
|release_c8_e1.25_r2.5_t1__risk0.5|-0.232%|-0.077%|-0.065%|5|fail|
|release_c8_e1.25_r2.5_t1__risk1|-0.565%|-0.189%|-0.191%|9|fail|
|release_c8_e1.25_r2.5_t1__risk1.5|-1.439%|-0.482%|-0.497%|11|fail|

Diagnostics do not replace a failed locked candidate. Full gate failures, monthly returns, conditional99% intervals, source/protocol/producer locks, primary trades and curves are in session-research.json.
All failed experiments remain registered. Historical screening does not establish stability, broker fills, prop payouts or forward profitability.
