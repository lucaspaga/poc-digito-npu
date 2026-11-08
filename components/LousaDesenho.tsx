import { memo, useEffect, useRef, useState } from 'react';
import {
  GestureResponderEvent,
  LayoutChangeEvent,
  PanResponder,
  StyleSheet,
  View,
} from 'react-native';
import Svg, { Circle, Path } from 'react-native-svg';

export type Ponto = [number, number];
export type Traco = Ponto[];
export type Tracos = Traco[];

type Props = {
  servidorDisponivel: boolean;
  limparQuandoMudar?: number;
  onTracosChange: (tracos: Tracos) => void;
  onTracoFim: (tracos: Tracos) => void;
};

function caminhoDoTraco(traco: Traco): string {
  if (traco.length === 0) {
    return '';
  }

  const [primeiroPonto, ...demaisPontos] = traco;
  return [
    `M ${primeiroPonto[0]} ${primeiroPonto[1]}`,
    ...demaisPontos.map((ponto) => `L ${ponto[0]} ${ponto[1]}`),
  ].join(' ');
}

function LousaDesenho({
  servidorDisponivel,
  limparQuandoMudar = 0,
  onTracosChange,
  onTracoFim,
}: Props) {
  const [tracos, setTracos] = useState<Tracos>([]);
  const tracosRef = useRef<Tracos>([]);
  const callbackRef = useRef(onTracosChange);
  const fimTracoRef = useRef(onTracoFim);
  const servidorDisponivelRef = useRef(servidorDisponivel);
  const tamanhoRef = useRef({ width: 0, height: 0 });
  const limparAnteriorRef = useRef(limparQuandoMudar);

  callbackRef.current = onTracosChange;
  fimTracoRef.current = onTracoFim;
  servidorDisponivelRef.current = servidorDisponivel;

  const atualizarTracos = (proximosTracos: Tracos) => {
    tracosRef.current = proximosTracos;
    setTracos(proximosTracos);
    callbackRef.current(proximosTracos);
  };

  const pontoDoEvento = (event: GestureResponderEvent): Ponto => {
    const { width, height } = tamanhoRef.current;
    const { locationX, locationY } = event.nativeEvent;

    return [
      Math.round(Math.max(0, Math.min(locationX, width))),
      Math.round(Math.max(0, Math.min(locationY, height))),
    ];
  };

  const iniciarTraco = (ponto: Ponto) => {
    atualizarTracos([...tracosRef.current, [ponto]]);
  };

  const adicionarPonto = (ponto: Ponto) => {
    const tracosAtuais = tracosRef.current;
    const ultimoTraco = tracosAtuais[tracosAtuais.length - 1];

    if (!ultimoTraco) {
      iniciarTraco(ponto);
      return;
    }

    atualizarTracos([
      ...tracosAtuais.slice(0, -1),
      [...ultimoTraco, ponto],
    ]);
  };

  const panResponder = useRef(
    PanResponder.create({
      onStartShouldSetPanResponder: () => servidorDisponivelRef.current,
      onMoveShouldSetPanResponder: () => servidorDisponivelRef.current,
      onPanResponderGrant: (event) => {
        if (servidorDisponivelRef.current) {
          iniciarTraco(pontoDoEvento(event));
        }
      },
      onPanResponderMove: (event) => {
        if (servidorDisponivelRef.current) {
          adicionarPonto(pontoDoEvento(event));
        }
      },
      onPanResponderRelease: () => {
        if (servidorDisponivelRef.current) {
          fimTracoRef.current(tracosRef.current);
        }
      },
      onPanResponderTerminate: () => {
        if (servidorDisponivelRef.current) {
          fimTracoRef.current(tracosRef.current);
        }
      },
    }),
  ).current;

  useEffect(() => {
    if (limparAnteriorRef.current === limparQuandoMudar) {
      return;
    }

    limparAnteriorRef.current = limparQuandoMudar;
    atualizarTracos([]);
  }, [limparQuandoMudar]);

  const aoMudarLayout = (event: LayoutChangeEvent) => {
    const { width, height } = event.nativeEvent.layout;
    tamanhoRef.current = { width, height };
  };

  return (
    <View
      {...panResponder.panHandlers}
      onLayout={aoMudarLayout}
      style={styles.lousa}
    >
      <Svg pointerEvents="none" style={StyleSheet.absoluteFill}>
        {tracos.map((traco, indice) => (
          <Path
            d={caminhoDoTraco(traco)}
            key={indice}
            fill="none"
            stroke="#39B9FF"
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={12}
          />
        ))}
        {tracos.map((traco, indice) => {
          const ponto = traco.length === 1 ? traco[0] : undefined;
          return ponto ? (
            <Circle
              cx={ponto[0]}
              cy={ponto[1]}
              fill="#39B9FF"
              key={`ponto-${indice}`}
              r={6}
            />
          ) : null;
        })}
      </Svg>
    </View>
  );
}

export default memo(LousaDesenho);

const styles = StyleSheet.create({
  lousa: {
    backgroundColor: '#0A1D30',
    borderColor: '#28648F',
    borderRadius: 12,
    borderWidth: 1,
    flex: 1,
    overflow: 'hidden',
  },
});