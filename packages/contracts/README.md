# Contratos compartilhados

Contratos neutros usados pela shell e pelos módulos.

Regras:

- schemas versionados;
- origem/proveniência obrigatória em observações;
- nenhum tipo pode importar implementação de um Core;
- mudanças incompatíveis exigem nova versão;
- campos não observáveis permanecem explicitamente indisponíveis.
