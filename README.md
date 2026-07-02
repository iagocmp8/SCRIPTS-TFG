# SCRIPTS-TFG
Achéganse os scripts usados para a toma de datos dos aparellos no setup do TFG: Caracterización Ambiental de electrónica para o futuro detector de vértices do LHCb: VELO Upgrade II

O primeiro é o código en C++ para manexar o Arduino ao que temos conectado o PT-100 (sensor de temperatura colocado donde o lpGBT)
O segundo é o script que toma os datos do PT-100, do MPT 200 (sensor presión cámara baleiro) e do sistema de refrixeración (chiller).


*NOTA*: 
A forma de conectarnos a estes sistemas é mediante USB a través dos propios portos Serie do ordenador. No programa só temos que indicar que porto Serie é polo que entran os datos de cada aparello (en Linux: '/dev/ttyUSB*'). Ao darlle a executar, a toma de datos é automática. Estes, según vaian chegando, serán gardados nun .csv (que terá no nome a data e hora exacta do inicio da toma de datos) e graficados en pantalla. 
