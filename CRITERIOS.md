# Critérios de aceitação

## Etapa 1: desenhar
- [ ] Durante a realização do desenho, os traços estão realmente aparecendo o seguindo o toque do usuário, mesmo com as inferências acontecendo.
- [ ] A lousa é apagada ao limpar e inferencias antigas relacionas ao numero de desenho atual sao descartadas de forma que a nada aparece em Predição do Desenho.

## Etapa 2: predição ao vivo
Com atraso: servidor atrasando cada resposta entre 0 e 0,5s, repetido em 10 desenhos seguidos.

- [ ] Com o servidor sem atraso, o número "Predição do desenho" muda sem tocar em nada, e no máximo a cada 0,5s enquanto desenho.
- [ ] Com o servidor atrasando, o número "Predição do desenho" deve mudar no máximo a cada 1s enquanto desenho.



## Etapa 3: respostas atrasadas e fora de ordem (responde à pergunta)
- [ ] Durante o desenho, o número "Predição do desenho" nunca diminui.
- [ ] Até 1s depois de parar de desenhar, o número "Predição do desenho" fica igual ao número "Desenho atual".

## Etapa 4: erros
- [ ] Led verde na tela para servidor ligado e vermelho para desligado, e em caso de desligamento a mudança de cores não passa de 4s.
- [ ] Caso o servidor desligue, botão de reconectar aparece na tela e a lousa fica inutilizavel. ao usuario clicar no botao, nova tentiva de conexao ocorre e em caso de sucesso, app se torna utilizável novamente e inferencias voltam a ocorrer.
- [ ] App envia mensagens claras de erro: "Erro ao realizar a inferência!( servidor respondeu com erro)", "Falha de comunicação com o servidor!" (Servidor Desligado) ou "Erro: Time-out" (demora maior que 5s).
- [ ] Em caso de falha, aviso aparece na uma mensagem na tela e a ultima previsao fica estatica até que as inferencias voltem a funcionar.

**Verificado em:** ( ) aparelho físico ( ) emulador
**Resultado:** ( ) passou ( ) reprovou
