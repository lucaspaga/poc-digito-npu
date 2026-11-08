## Convenções deste projeto

- Não altere arquivos fora do escopo pedido. Explique cada alteração.
- Componentes ficam em `components/`, um arquivo por componente.
- Estado nunca é modificado no lugar: sempre gere um novo valor.
- Valores que podem ser calculados a partir do estado não viram estado.
- Antes de usar um pacote, confirme na documentação se ele funciona no Expo Go.

## Contexto desta prova de conceito

- TCC: plataforma didática com um SoC RISC-V em FPGA e uma NPU que executa uma rede neural para reconhecer dígitos (MNIST).
- Problema: mostrar no celular a predição enquanto o usuário desenha o dígito, com as inferências passando pela rede e podendo voltar atrasadas, fora de ordem ou com erro. Uma resposta antiga não pode substituir a predição do desenho atual.
- Tecnologia investigada: `@tanstack/react-query`, comparada com `fetch` e `AbortController`.
- Uma tela só, em `App.tsx`: o usuário desenha um dígito e vê a predição, a confiança e a origem do resultado.
- A NPU é emulada por um servidor Python no computador, porque a PoC é feita sem a placa. O endereço do servidor vem de `EXPO_PUBLIC_SERVIDOR`, nunca de `localhost`.
- O app roda no Expo Go, em um iPhone.
- Não usar Expo Router: esta PoC tem uma tela só. Ignore a seção "Navigation & Routing" acima e não crie a pasta `src/app/`.
- Fora de escopo: login, salvar dados, design final e tudo que não demonstre a pergunta.
