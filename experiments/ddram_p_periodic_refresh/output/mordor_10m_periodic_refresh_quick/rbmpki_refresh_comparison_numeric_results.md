# DDRAM-P periodic-refresh comparison

Refresh overhead is `100 × (refresh cycles / matching no-refresh cycles − 1)`.
Arithmetic means summarize percentage points; GMean is computed over cycle ratios.

## Low RBMPKI (n=4)

### 1 view

| Workload | Refresh | No-refresh cycles | Refresh cycles | Overhead | Row-hit rate | REFab served | Internal refreshes | ACT NACKs |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 538.imagick | Periodic REFab | 2,540,598 | 2,586,153 | +1.7931% | 0.6623% | 103 | 0 | 0 |
| 538.imagick | Oracle | 2,540,598 | 2,568,758 | +1.1084% | 0.6623% | 0 | 3,264 | 0 |
| 538.imagick | NACK | 2,540,598 | 2,568,758 | +1.1084% | 0.6623% | 0 | 3,264 | 968 |
| 403.gcc | Periodic REFab | 2,714,525 | 2,768,021 | +1.9707% | 56.8190% | 110 | 0 | 0 |
| 403.gcc | Oracle | 2,714,525 | 2,730,232 | +0.5786% | 55.8980% | 0 | 3,488 | 0 |
| 403.gcc | NACK | 2,714,525 | 2,730,232 | +0.5786% | 55.8980% | 0 | 3,488 | 2,873 |
| 401.bzip2 | Periodic REFab | 3,932,171 | 4,026,811 | +2.4068% | 55.9523% | 161 | 0 | 0 |
| 401.bzip2 | Oracle | 3,932,171 | 3,917,451 | -0.3743% | 56.1257% | 0 | 4,992 | 0 |
| 401.bzip2 | NACK | 3,932,171 | 3,924,579 | -0.1931% | 56.1002% | 0 | 4,992 | 17,786 |
| ycsb_aserver | Periodic REFab | 6,000,098 | 6,267,522 | +4.4570% | 64.9930% | 250 | 0 | 0 |
| ycsb_aserver | Oracle | 6,000,098 | 5,987,522 | -0.2096% | 65.1894% | 0 | 7,648 | 0 |
| ycsb_aserver | NACK | 6,000,098 | 5,987,522 | -0.2096% | 65.1337% | 0 | 7,648 | 41,413 |

| Refresh | Mean overhead | Cycle-ratio GMean overhead |
|---|---:|---:|
| Periodic REFab | +2.6569% | +2.6514% |
| Oracle | +0.2758% | +0.2740% |
| NACK | +0.3211% | +0.3196% |

### 2 views

| Workload | Refresh | No-refresh cycles | Refresh cycles | Overhead | Row-hit rate | REFab served | Internal refreshes | ACT NACKs |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 538.imagick | Periodic REFab | 2,539,974 | 2,586,153 | +1.8181% | 0.6623% | 103 | 0 | 0 |
| 538.imagick | Oracle | 2,539,974 | 2,540,342 | +0.0145% | 89.4040% | 0 | 3,232 | 0 |
| 538.imagick | NACK | 2,539,974 | 2,540,358 | +0.0151% | 89.4040% | 0 | 3,232 | 3 |
| 403.gcc | Periodic REFab | 2,684,882 | 2,742,831 | +2.1583% | 59.5820% | 109 | 0 | 0 |
| 403.gcc | Oracle | 2,684,882 | 2,685,874 | +0.0369% | 72.0510% | 0 | 3,424 | 0 |
| 403.gcc | NACK | 2,684,882 | 2,689,282 | +0.1639% | 71.0592% | 0 | 3,424 | 394 |
| 401.bzip2 | Periodic REFab | 3,812,939 | 3,866,336 | +1.4004% | 63.5673% | 154 | 0 | 0 |
| 401.bzip2 | Oracle | 3,812,939 | 3,759,421 | -1.4036% | 65.9543% | 0 | 4,800 | 0 |
| 401.bzip2 | NACK | 3,812,939 | 3,760,797 | -1.3675% | 65.4800% | 0 | 4,800 | 1,879 |
| ycsb_aserver | Periodic REFab | 5,848,690 | 5,913,325 | +1.1051% | 68.4004% | 236 | 0 | 0 |
| ycsb_aserver | Oracle | 5,848,690 | 5,693,349 | -2.6560% | 67.8145% | 0 | 7,264 | 0 |
| ycsb_aserver | NACK | 5,848,690 | 5,705,589 | -2.4467% | 67.6443% | 0 | 7,296 | 4,510 |

| Refresh | Mean overhead | Cycle-ratio GMean overhead |
|---|---:|---:|
| Periodic REFab | +1.6205% | +1.6197% |
| Oracle | -1.0020% | -1.0084% |
| NACK | -0.9088% | -0.9146% |

## Medium RBMPKI (n=3)

### 1 view

| Workload | Refresh | No-refresh cycles | Refresh cycles | Overhead | Row-hit rate | REFab served | Internal refreshes | ACT NACKs |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| stream_10.trace | Periodic REFab | 28,672,718 | 30,436,966 | +6.1531% | 98.2706% | 1,217 | 0 | 0 |
| stream_10.trace | Oracle | 28,672,718 | 28,409,300 | -0.9187% | 98.3750% | 0 | 36,352 | 0 |
| stream_10.trace | NACK | 28,672,718 | 28,409,342 | -0.9186% | 98.3750% | 0 | 36,352 | 178,415 |
| tpcc64 | Periodic REFab | 6,157,517 | 6,412,699 | +4.1442% | 72.9953% | 256 | 0 | 0 |
| tpcc64 | Oracle | 6,157,517 | 6,091,267 | -1.0759% | 73.1656% | 0 | 7,776 | 0 |
| tpcc64 | NACK | 6,157,517 | 6,100,941 | -0.9188% | 73.1382% | 0 | 7,808 | 43,052 |
| 557.xz | Periodic REFab | 6,146,281 | 6,416,555 | +4.3974% | 13.7851% | 256 | 0 | 0 |
| 557.xz | Oracle | 6,146,281 | 6,136,953 | -0.1518% | 13.8113% | 0 | 7,840 | 0 |
| 557.xz | NACK | 6,146,281 | 6,136,955 | -0.1517% | 13.8200% | 0 | 7,840 | 45,010 |

| Refresh | Mean overhead | Cycle-ratio GMean overhead |
|---|---:|---:|
| Periodic REFab | +4.8982% | +4.8944% |
| Oracle | -0.7155% | -0.7163% |
| NACK | -0.6630% | -0.6637% |

### 2 views

| Workload | Refresh | No-refresh cycles | Refresh cycles | Overhead | Row-hit rate | REFab served | Internal refreshes | ACT NACKs |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| stream_10.trace | Periodic REFab | 28,670,926 | 30,436,966 | +6.1597% | 98.2706% | 1,217 | 0 | 0 |
| stream_10.trace | Oracle | 28,670,926 | 27,902,665 | -2.6796% | 98.4372% | 0 | 35,712 | 0 |
| stream_10.trace | NACK | 28,670,926 | 27,907,393 | -2.6631% | 98.4373% | 0 | 35,712 | 546 |
| tpcc64 | Periodic REFab | 5,854,088 | 5,947,176 | +1.5901% | 75.3501% | 237 | 0 | 0 |
| tpcc64 | Oracle | 5,854,088 | 5,683,813 | -2.9087% | 75.7930% | 0 | 7,264 | 0 |
| tpcc64 | NACK | 5,854,088 | 5,689,147 | -2.8175% | 75.8541% | 0 | 7,264 | 8,259 |
| 557.xz | Periodic REFab | 5,956,937 | 6,022,081 | +1.0936% | 15.7743% | 240 | 0 | 0 |
| 557.xz | Oracle | 5,956,937 | 5,836,433 | -2.0229% | 15.7423% | 0 | 7,456 | 0 |
| 557.xz | NACK | 5,956,937 | 5,844,929 | -1.8803% | 15.6434% | 0 | 7,456 | 11,915 |

| Refresh | Mean overhead | Cycle-ratio GMean overhead |
|---|---:|---:|
| Periodic REFab | +2.9478% | +2.9228% |
| Oracle | -2.5371% | -2.5378% |
| NACK | -2.4536% | -2.4545% |

## High RBMPKI (n=3)

### 1 view

| Workload | Refresh | No-refresh cycles | Refresh cycles | Overhead | Row-hit rate | REFab served | Internal refreshes | ACT NACKs |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 520.omnetpp | Periodic REFab | 13,119,300 | 13,958,631 | +6.3977% | 35.3037% | 558 | 0 | 0 |
| 520.omnetpp | Oracle | 13,119,300 | 13,232,543 | +0.8632% | 35.3804% | 0 | 16,928 | 0 |
| 520.omnetpp | NACK | 13,119,300 | 13,236,122 | +0.8905% | 35.3763% | 0 | 16,928 | 134,204 |
| 470.lbm | Periodic REFab | 25,074,276 | 27,499,001 | +9.6702% | 61.4862% | 1,099 | 0 | 0 |
| 470.lbm | Oracle | 25,074,276 | 26,012,868 | +3.7432% | 61.5769% | 0 | 33,280 | 0 |
| 470.lbm | NACK | 25,074,276 | 26,029,207 | +3.8084% | 61.6392% | 0 | 33,312 | 330,015 |
| 429.mcf | Periodic REFab | 33,143,450 | 35,985,738 | +8.5757% | 18.3747% | 1,439 | 0 | 0 |
| 429.mcf | Oracle | 33,143,450 | 34,018,628 | +2.6406% | 18.4676% | 0 | 43,520 | 0 |
| 429.mcf | NACK | 33,143,450 | 34,081,559 | +2.8305% | 18.4440% | 0 | 43,616 | 426,454 |

| Refresh | Mean overhead | Cycle-ratio GMean overhead |
|---|---:|---:|
| Periodic REFab | +8.2145% | +8.2059% |
| Oracle | +2.4157% | +2.4088% |
| NACK | +2.5098% | +2.5026% |

### 2 views

| Workload | Refresh | No-refresh cycles | Refresh cycles | Overhead | Row-hit rate | REFab served | Internal refreshes | ACT NACKs |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 520.omnetpp | Periodic REFab | 12,469,172 | 12,747,463 | +2.2318% | 40.1236% | 509 | 0 | 0 |
| 520.omnetpp | Oracle | 12,469,172 | 12,220,495 | -1.9943% | 39.0817% | 0 | 15,616 | 0 |
| 520.omnetpp | NACK | 12,469,172 | 12,220,300 | -1.9959% | 39.1568% | 0 | 15,616 | 41,271 |
| 470.lbm | Periodic REFab | 18,739,903 | 20,083,911 | +7.1719% | 84.1189% | 803 | 0 | 0 |
| 470.lbm | Oracle | 18,739,903 | 18,822,471 | +0.4406% | 81.6236% | 0 | 24,064 | 0 |
| 470.lbm | NACK | 18,739,903 | 18,886,633 | +0.7830% | 81.4011% | 0 | 24,160 | 68,460 |
| 429.mcf | Periodic REFab | 29,178,226 | 31,562,935 | +8.1729% | 19.6552% | 1,262 | 0 | 0 |
| 429.mcf | Oracle | 29,178,226 | 29,601,458 | +1.4505% | 20.0373% | 0 | 37,888 | 0 |
| 429.mcf | NACK | 29,178,226 | 29,683,191 | +1.7306% | 20.0582% | 0 | 37,984 | 238,967 |

| Refresh | Mean overhead | Cycle-ratio GMean overhead |
|---|---:|---:|
| Periodic REFab | +5.8589% | +5.8267% |
| Oracle | -0.0344% | -0.0449% |
| NACK | +0.1726% | +0.1600% |

## All workloads

| Views | Refresh | Mean overhead | Cycle-ratio GMean overhead |
|---:|---|---:|---:|
| 1 | Periodic REFab | +4.9966% | +4.9656% |
| 1 | Oracle | +0.6204% | +0.6097% |
| 1 | NACK | +0.6825% | +0.6716% |
| 2 | Periodic REFab | +3.2902% | +3.2579% |
| 2 | Oracle | -1.1723% | -1.1830% |
| 2 | NACK | -1.0478% | -1.0594% |
