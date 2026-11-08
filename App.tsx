import { StatusBar } from 'expo-status-bar';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Button, StyleSheet, Text, View } from 'react-native';
import { SafeAreaProvider, SafeAreaView } from 'react-native-safe-area-context';
import LousaDesenho, { Tracos } from './components/LousaDesenho';

type RespostaInferencia = {
  revisao: number;
  classe: number;
  confianca: number;
  origem: string;
};

const INTERVALO_INFERENCIA_MS = 200;
const TIMEOUT_INFERENCIA_MS = 5000;
const INTERVALO_STATUS_MS = 2000;
const TIMEOUT_STATUS_MS = 1000;

export default function App() {
  const tracosRef = useRef<Tracos>([]);
  const revisaoRef = useRef(0);
  const desenhoIdRef = useRef(0);
  const ultimaRevisaoEnviadaRef = useRef(0);
  const proximaInferenciaRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const ultimaTentativaRef = useRef(0);
  const controladorRef = useRef<AbortController | null>(null);
  const temporizadoresInferenciaRef = useRef(
    new Map<AbortController, ReturnType<typeof setTimeout>>(),
  );
  const timeoutsInferenciaRef = useRef(new WeakSet<AbortController>());
  const statusEmAndamentoRef = useRef(false);
  const controladorStatusRef = useRef<AbortController | null>(null);
  const intervaloStatusRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [revisao, setRevisao] = useState(0);
  const [predicao, setPredicao] = useState<RespostaInferencia | null>(null);
  const predicaoRef = useRef<RespostaInferencia | null>(null);
  const [enviadas, setEnviadas] = useState(0);
  const [erros, setErros] = useState(0);
  const [descartadas, setDescartadas] = useState(0);
  const [canceladas, setCanceladas] = useState(0);
  const [voltouAtras, setVoltouAtras] = useState(0);
  const [limparQuandoMudar, setLimparQuandoMudar] = useState(0);
  const [servidorDisponivel, setServidorDisponivel] = useState(false);
  const [mensagem, setMensagem] = useState<string | null>(null);

  const enviarInferencia = useCallback(() => {
    const tracos = tracosRef.current;
    const revisaoParaEnviar = revisaoRef.current;

    if (tracos.length === 0 || revisaoParaEnviar === ultimaRevisaoEnviadaRef.current) {
      return;
    }

    ultimaRevisaoEnviadaRef.current = revisaoParaEnviar;
    ultimaTentativaRef.current = Date.now();
    setEnviadas((valor) => valor + 1);

    if (controladorRef.current !== null) {
      const temporizadorAnterior = temporizadoresInferenciaRef.current.get(controladorRef.current);
      if (temporizadorAnterior !== undefined) {
        clearTimeout(temporizadorAnterior);
        temporizadoresInferenciaRef.current.delete(controladorRef.current);
      }
      controladorRef.current.abort();
    }

    const controlador = new AbortController();
    const desenhoDoEnvio = desenhoIdRef.current;
    controladorRef.current = controlador;
    const temporizador = setTimeout(() => {
      timeoutsInferenciaRef.current.add(controlador);
      controlador.abort();
    }, TIMEOUT_INFERENCIA_MS);
    temporizadoresInferenciaRef.current.set(controlador, temporizador);

    const servidor = process.env.EXPO_PUBLIC_SERVIDOR ?? '';
    fetch(`${servidor.replace(/\/$/, '')}/inferir/digito`, {
      signal: controlador.signal,
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ revisao: revisaoParaEnviar, tracos }),
    })
      .then(async (resposta) => {
        if (!resposta.ok) {
          throw new Error('erro-inferencia');
        }
        return resposta.json() as Promise<RespostaInferencia>;
      })
      .then((resposta) => {
        if (desenhoDoEnvio !== desenhoIdRef.current) {
          return;
        }

        setMensagem(null);
        const revisaoExibida = predicaoRef.current?.revisao ?? 0;
        if (resposta.revisao < revisaoExibida) {
          setVoltouAtras((valor) => valor + 1);
        }
        if (resposta.revisao <= revisaoExibida) {
          setDescartadas((valor) => valor + 1);
          return;
        }

        predicaoRef.current = resposta;
        setPredicao(resposta);
      })
      .catch((erro: unknown) => {
        if (controlador.signal.aborted) {
          if (desenhoDoEnvio === desenhoIdRef.current) {
            if (timeoutsInferenciaRef.current.has(controlador)) {
              setErros((valor) => valor + 1);
              setMensagem('Erro: Time-out');
            } else {
              setCanceladas((valor) => valor + 1);
            }
          }
          return;
        }
        if (desenhoDoEnvio === desenhoIdRef.current) {
          setErros((valor) => valor + 1);
          setMensagem(erro instanceof Error && erro.message === 'erro-inferencia'
            ? 'Erro ao realizar a inferência!'
            : 'Falha de comunicação com o servidor!');
        }
      })
      .finally(() => {
        const temporizadorAtual = temporizadoresInferenciaRef.current.get(controlador);
        if (temporizadorAtual !== undefined) {
          clearTimeout(temporizadorAtual);
          temporizadoresInferenciaRef.current.delete(controlador);
        }
        if (controladorRef.current === controlador) {
          controladorRef.current = null;
        }
      });
  }, []);

  const agendarInferencia = useCallback(() => {
    if (proximaInferenciaRef.current !== null) {
      return;
    }

    const atraso = Math.max(
      0,
      INTERVALO_INFERENCIA_MS - (Date.now() - ultimaTentativaRef.current),
    );
    proximaInferenciaRef.current = setTimeout(() => {
      proximaInferenciaRef.current = null;
      enviarInferencia();
    }, atraso);
  }, [enviarInferencia]);

  const aoMudarTracos = useCallback((tracos: Tracos) => {
    tracosRef.current = tracos;
    if (tracos.length === 0) {
      revisaoRef.current = 0;
      setRevisao(0);
      return;
    }
    revisaoRef.current += 1;
    setRevisao(revisaoRef.current);
    agendarInferencia();
  }, [agendarInferencia]);

  const aoTerminarTraco = useCallback((tracos: Tracos) => {
    tracosRef.current = tracos;
    if (revisaoRef.current !== ultimaRevisaoEnviadaRef.current) {
      if (proximaInferenciaRef.current !== null) {
        clearTimeout(proximaInferenciaRef.current);
        proximaInferenciaRef.current = null;
      }
      enviarInferencia();
    }
  }, [enviarInferencia]);

  const consultarStatus = useCallback(async () => {
    if (statusEmAndamentoRef.current) {
      return;
    }

    statusEmAndamentoRef.current = true;
    const controlador = new AbortController();
    controladorStatusRef.current = controlador;
    const temporizador = setTimeout(() => controlador.abort(), TIMEOUT_STATUS_MS);

    try {
      const servidor = process.env.EXPO_PUBLIC_SERVIDOR ?? '';
      const resposta = await fetch(`${servidor.replace(/\/$/, '')}/status`, {
        signal: controlador.signal,
      });
      if (!resposta.ok) {
        throw new Error('status-invalido');
      }
      setServidorDisponivel(true);
      setMensagem(null);
      if (intervaloStatusRef.current === null) {
        intervaloStatusRef.current = setInterval(consultarStatus, INTERVALO_STATUS_MS);
      }
    } catch {
      setServidorDisponivel(false);
      setMensagem('Falha de comunicação com o servidor!');
      if (intervaloStatusRef.current !== null) {
        clearInterval(intervaloStatusRef.current);
        intervaloStatusRef.current = null;
      }
    } finally {
      clearTimeout(temporizador);
      statusEmAndamentoRef.current = false;
      if (controladorStatusRef.current === controlador) {
        controladorStatusRef.current = null;
      }
    }
  }, []);

  useEffect(() => {
    consultarStatus();

    return () => {
      if (intervaloStatusRef.current !== null) {
        clearInterval(intervaloStatusRef.current);
      }
      controladorStatusRef.current?.abort();
      if (proximaInferenciaRef.current !== null) {
        clearTimeout(proximaInferenciaRef.current);
      }
      controladorRef.current?.abort();
      temporizadoresInferenciaRef.current.forEach((temporizador) => {
        clearTimeout(temporizador);
      });
      temporizadoresInferenciaRef.current.clear();
    };
  }, [consultarStatus]);

  const limpar = () => {
    if (proximaInferenciaRef.current !== null) {
      clearTimeout(proximaInferenciaRef.current);
      proximaInferenciaRef.current = null;
    }
    if (controladorRef.current !== null) {
      const temporizador = temporizadoresInferenciaRef.current.get(controladorRef.current);
      if (temporizador !== undefined) {
        clearTimeout(temporizador);
        temporizadoresInferenciaRef.current.delete(controladorRef.current);
      }
      controladorRef.current.abort();
      controladorRef.current = null;
    }
    tracosRef.current = [];
    desenhoIdRef.current += 1;
    revisaoRef.current = 0;
    ultimaRevisaoEnviadaRef.current = 0;
    setRevisao(0);
    predicaoRef.current = null;
    setPredicao(null);
    setEnviadas(0);
    setErros(0);
    setDescartadas(0);
    setCanceladas(0);
    setVoltouAtras(0);
    setMensagem(null);
    setLimparQuandoMudar((valor) => valor + 1);
  };

  return (
    <SafeAreaProvider>
      <SafeAreaView style={styles.container}>
        <View style={styles.conteudo}>
          <LousaDesenho
            servidorDisponivel={servidorDisponivel}
            limparQuandoMudar={limparQuandoMudar}
            onTracosChange={aoMudarTracos}
            onTracoFim={aoTerminarTraco}
          />
          <View style={styles.statusServidor}>
            <View
              style={[
                styles.led,
                servidorDisponivel ? styles.ledLigado : styles.ledDesligado,
              ]}
            />
            <Text>{servidorDisponivel ? 'Servidor ligado' : 'Servidor desligado'}</Text>
          </View>
          <View style={styles.informacoes}>
            <Text>Predição: {predicao?.classe ?? '-'}</Text>
            <Text>Confiança: {predicao ? `${(predicao.confianca * 100).toFixed(1)}%` : '-'}</Text>
            <Text>Origem: {predicao?.origem ?? '-'}</Text>
            <Text>Desenho atual: {revisao}</Text>
            <Text>Predição do desenho: {predicao?.revisao ?? 0}</Text>
            <Text>Enviadas: {enviadas}</Text>
            <Text>Erros: {erros}</Text>
            <Text>Descartadas: {descartadas}</Text>
            <Text>Canceladas: {canceladas}</Text>
            <Text>Voltou atrás: {voltouAtras}</Text>
            {mensagem ? <Text style={styles.mensagem}>{mensagem}</Text> : null}
          </View>
          <View style={styles.botao}>
            <Button onPress={limpar} title="Limpar" />
            {!servidorDisponivel ? (
              <Button onPress={consultarStatus} title="Reconectar" />
            ) : null}
          </View>
        </View>
        <StatusBar style="auto" />
      </SafeAreaView>
    </SafeAreaProvider>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#FFFFFF',
  },
  conteudo: {
    flex: 1,
    gap: 16,
    padding: 16,
  },
  botao: {
    alignSelf: 'stretch',
  },
  informacoes: {
    gap: 4,
  },
  statusServidor: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 8,
  },
  led: {
    borderRadius: 8,
    height: 16,
    width: 16,
  },
  ledLigado: {
    backgroundColor: '#22A447',
  },
  ledDesligado: {
    backgroundColor: '#D93434',
  },
  mensagem: {
    color: '#B42318',
  },
});
