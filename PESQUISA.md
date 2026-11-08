# Diário de pesquisa

## Contexto do TCC
Plataforma didática com um SoC RISC-V em FPGA e uma NPU que executa uma rede neural para reconhecer dígitos. Hoje a demonstração depende de um programa no computador, e o Digit Tracker já faz inferência ao vivo, mas sem rede entre a interface e a NPU.

## Pergunta de pesquisa
**Inicial:** Como o `@tanstack/react-query` permite que um app Expo mostre ao vivo a predição da NPU enquanto o usuário desenha um dígito no celular, na condição de as inferências irem pela rede a cada 0,2 s e poderem voltar atrasadas, fora de ordem ou com erro?

**Refinada:** O `@tanstack/react-query` é necessário para manter a predição ao vivo coerente com o desenho atual, na condição de as inferências irem pela rede a cada 0,2 s e voltarem atrasadas, fora de ordem ou com erro, ou `fetch` com `AbortController` e um número de revisão bastam?


## O que as IAs disseram
Mesmo pedido no ChatGPT e no Gemini.
- **Concordam:** cancelar não é a primeira escolha do `react-query`; as duas apontam `fetch` e `AbortController` como caminho direto.
- **Divergem:** só o ChatGPT trata o número de revisão como obrigatório, compara `useQuery` e `useMutation` e alerta sobre o Expo Go no SDK 58.
- **Documentação:** confirmou o limite do Expo Go na App Store e o `AbortSignal`; desmentiu o cancelamento automático citado pelo Gemini.


## Alternativas consideradas
| Opção | Serve para | Funciona no Expo Go? | Decisão |
|---|---|---|---|
| `fetch` + `AbortController` | | | |
| hook próprio `useFetch` | | | |
| `@tanstack/react-query` | | | |

## Fontes oficiais lidas

### Expo
- Project is incompatible with this version of Expo Go (https://docs.expo.dev/troubleshooting/expo-go-version-mismatch/)
- Expo Go sign-in required (https://docs.expo.dev/troubleshooting/expo-go-sign-in-required.md)
- Expo Network, SDK 58 (https://docs.expo.dev/versions/v58.0.0/sdk/network/)
- react-native-svg, SDK 58 (https://docs.expo.dev/versions/v58.0.0/sdk/svg/)
- react-native-safe-area-context, SDK 58 (https://docs.expo.dev/versions/v58.0.0/sdk/safe-area-context/)

### React Native
- Networking (https://reactnative.dev/docs/network)
- PanResponder (https://reactnative.dev/docs/panresponder)

### React
- Reusing Logic with Custom Hooks (https://react.dev/learn/reusing-logic-with-custom-hooks)

### TanStack Query
- Query Cancellation (https://tanstack.com/query/latest/docs/framework/react/guides/query-cancellation)
- Mutations (https://tanstack.com/query/latest/docs/framework/react/guides/mutations)
- useMutation (https://tanstack.com/query/latest/docs/framework/react/reference/useMutation)

### MDN
- AbortController (https://developer.mozilla.org/en-US/docs/Web/API/AbortController)


## Onde a IA errou
| O que pedi | O que veio | Como percebi | O que era o certo |
|---|---|---|---|
| Ler a documentação do Expo sobre requisições de rede (Copilot) | A página do Expo Network | Comparando o assunto da página com o pedido | A página trata do estado da rede do aparelho; ela não ensina a fazer requisições |
| Mapa do tema (Gemini) | Disse que o `react-query` cancela automaticamente quando uma nova requisição é disparada | Li Query Cancellation | Por padrão não cancela; é preciso usar o `signal` |
| Mapa do tema (ChatGPT) | Disse que `useMutation` exige controle próprio contra respostas antigas | Li a página de Mutations | Callbacks do `mutate` só rodam para a última chamada |
| Adaptar o servidor mantendo o modo --placa (Copilot) | Removeu o `import numpy` e afirmou que o modo continuaria compatível, mas o modo ainda usava `np.argmax` | Revisão do diff, sem executar o modo placa | Manter o import; o `NameError` só apareceria com a placa ligada |
| Contar cancelamentos (Copilot) | Identificou o cancelamento só por `erro.name === 'AbortError'`, e o contador ficou em 0 | O valor era impossível com esse atraso; revisão do código e novo teste | Usar `controlador.signal.aborted`; o contador passou a registrar 5, 2 e 7 |


## Limitações
- A inferência roda em uma emulação, não na NPU real.
- A documentação do Expo diz que o Expo Go da App Store para no SDK 54, mas este projeto SDK 58 abriu no iPhone sem TestFlight. Não encontrei a explicação; o funcionamento foi verificado no aparelho.


## Resultado e próximos passos no TCC
### Versão sem proteção
- Condição: servidor com atraso aleatório de 0 a 0,5 s, em 10 desenhos, no iPhone.
- O contador "Voltou atrás" chegou a 8 em um único desenho, ou seja, respostas antigas sobrescreveram a predição mais recente.
- O traço continuou fluido durante os envios.
- Com atraso fixo de 2 s, ao limpar logo depois de desenhar a predição de uma resposta atrasada apareceu na tela já limpa.
### Versão com proteção (`fetch`, `AbortController` e número de revisão)
- Mesma condição: atraso aleatório de 0 a 0,5 s, em 10 desenhos, no iPhone.
- "Voltou atrás" ficou em [valor], contra até 8 na versão sem proteção.
- As requisições antigas foram canceladas (5, 2 e 7 em três desenhos) antes de responder, então "Descartadas" ficou em 0.
- O número "Predição do desenho" não ficou mais de 1 s sem mudar e igualou "Desenho atual" em até 1 s depois de levantar o dedo.
- Com atraso fixo de 2 s, nada apareceu depois de limpar.

**Resposta parcial:** nessa condição, o `react-query` não foi necessário. O teste não avalia o `react-query` em si, nem atrasos maiores.



