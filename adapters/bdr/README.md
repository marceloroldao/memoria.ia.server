# Adaptador BDR

Ponte entre o BDR Explorer e contratos públicos do Resolutive DB.

O adaptador deve oferecer snapshots, capacidades e eventos observáveis. Não pode analisar diretamente WAL, snapshots, índices privados ou arquivos internos. Ausência de telemetria pública deve ser reportada como capacidade indisponível.
