import { StatusBar } from 'expo-status-bar';
import { useRef, useState } from 'react';
import { Button, StyleSheet, View } from 'react-native';
import { SafeAreaProvider, SafeAreaView } from 'react-native-safe-area-context';
import LousaDesenho, { Tracos } from './components/LousaDesenho';

export default function App() {
  const tracosRef = useRef<Tracos>([]);
  const [limparQuandoMudar, setLimparQuandoMudar] = useState(0);

  return (
    <SafeAreaProvider>
      <SafeAreaView style={styles.container}>
        <View style={styles.conteudo}>
          <LousaDesenho
            limparQuandoMudar={limparQuandoMudar}
            onTracosChange={(tracos) => {
              tracosRef.current = tracos;
            }}
          />
          <View style={styles.botao}>
            <Button
              onPress={() => setLimparQuandoMudar((valor) => valor + 1)}
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
});
