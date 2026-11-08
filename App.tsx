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

export default function App() {
  const tracosRef = useRef<Tracos>([]);
  const revisaoRef = useRef(0);
  const ultimaRevisaoEnviadaRef = useRef(0);
  const proximaInferenciaRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const ultimaTentativaRef = useRef(0);
  const [revisao, setRevisao] = useState(0);
  const [predicao, setPredicao] = useState<RespostaInferencia | null>(null);
  const predicaoRef = useRef<RespostaInferencia | null>(null);
  const [enviadas, setEnviadas] = useState(0);
  const [erros, setErros] = useState(0);
  const [voltouAtras, setVoltouAtras] = useState(0);
  const [limparQuandoMudar, setLimparQuandoMudar] = useState(0);

  const enviarInferencia = useCallback(() => {
    const tracos = tracosRef.current;
    const revisaoParaEnviar = revisaoRef.current;

    if (tracos.length === 0 || revisaoParaEnviar === ultimaRevisaoEnviadaRef.current) {
      return;
    }

    ultimaRevisaoEnviadaRef.current = revisaoParaEnviar;
    ultimaTentativaRef.current = Date.now();
    setEnviadas((valor) => valor + 1);

    const servidor = process.env.EXPO_PUBLIC_SERVIDOR ?? '';
    fetch(`${servidor.replace(/\/$/, '')}/inferir/digito`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ revisao: revisaoParaEnviar, tracos }),
    })
      .then(async (resposta) => {
        if (!resposta.ok) {
          throw new Error(`HTTP ${resposta.status}`);
        }
        return resposta.json() as Promise<RespostaInferencia>;
      })
      .then((resposta) => {
        if (predicaoRef.current && resposta.revisao < predicaoRef.current.revisao) {
          setVoltouAtras((valor) => valor + 1);
        }
        predicaoRef.current = resposta;
        setPredicao(resposta);
      })
      .catch(() => setErros((valor) => valor + 1));
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

  useEffect(() => () => {
    if (proximaInferenciaRef.current !== null) {
      clearTimeout(proximaInferenciaRef.current);
    }
  }, []);

  const limpar = () => {
    if (proximaInferenciaRef.current !== null) {
      clearTimeout(proximaInferenciaRef.current);
      proximaInferenciaRef.current = null;
    }
    tracosRef.current = [];
    revisaoRef.current = 0;
    ultimaRevisaoEnviadaRef.current = 0;
    setRevisao(0);
    predicaoRef.current = null;
    setPredicao(null);
    setEnviadas(0);
    setErros(0);
    setVoltouAtras(0);
    setLimparQuandoMudar((valor) => valor + 1);
  };

  return (
    <SafeAreaProvider>
      <SafeAreaView style={styles.container}>
        <View style={styles.conteudo}>
          <LousaDesenho
            limparQuandoMudar={limparQuandoMudar}
            onTracosChange={aoMudarTracos}
            onTracoFim={aoTerminarTraco}
          />
          <View style={styles.informacoes}>
            <Text>Predição: {predicao?.classe ?? '-'}</Text>
            <Text>Confiança: {predicao ? `${(predicao.confianca * 100).toFixed(1)}%` : '-'}</Text>
            <Text>Origem: {predicao?.origem ?? '-'}</Text>
            <Text>Desenho atual: {revisao}</Text>
            <Text>Predição do desenho: {predicao?.revisao ?? 0}</Text>
            <Text>Enviadas: {enviadas}</Text>
            <Text>Erros: {erros}</Text>
            <Text>Voltou atrás: {voltouAtras}</Text>
          </View>
          <View style={styles.botao}>
            <Button
              onPress={limpar}
              title="Limpar"
            />
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
});
