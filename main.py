import os
import pandas as pd
from pysus.online_data import SIM, SINASC, SIH

# 1. Configurar o caminho base na sua máquina local
# Isso cria a pasta 'dados_datasus' no mesmo local onde este script está rodando
base_path = os.path.join(os.getcwd(), 'dados_datasus')

# Sistemas que vamos iterar e suas respectivas configurações
sistemas_config = {
    'SINASC': {'func': SINASC.download, 'mensal': False, 'groups': 'DN'},  # DN = Declaração de Nascido Vivo
    'SIM': {'func': SIM.download, 'mensal': False, 'groups': 'CID10'},  # CID10 = dados a partir de 1996
    'SIH': {'func': SIH.download, 'mensal': True, 'groups': 'RD'}  # RD = AIH Reduzida
}


def configurar_pastas(sistemas):
    """Cria a estrutura de diretórios para cada sistema localmente."""
    for sistema in sistemas:
        caminho_sistema = os.path.join(base_path, sistema)
        os.makedirs(caminho_sistema, exist_ok=True)
    print(f"Estrutura de pastas verificada/criada em: {base_path}")


def baixar_e_salvar_dados(estados, anos):
    configurar_pastas(sistemas_config.keys())

    for estado in estados:
        for ano in anos:
            for sistema, config in sistemas_config.items():
                caminho_destino = os.path.join(base_path, sistema)

                print(f"[{sistema}] Iniciando extração: {estado} - {ano}...")

                try:
                    if not config['mensal']:
                        # Para SIM e SINASC (Anual)
                        # Assinatura correta: download(groups, states, years, data_dir)
                        parquet_set = config['func'](
                            groups=config['groups'],
                            states=estado,
                            years=ano
                        )

                        # A função retorna um ParquetSet, use to_dataframe() diretamente
                        if parquet_set:
                            df = parquet_set.to_dataframe()

                            if not df.empty:
                                filename = f"{sistema}_{estado}_{ano}.parquet"
                                file_full_path = os.path.join(caminho_destino, filename)
                                df.to_parquet(file_full_path, index=False)
                                print(f"Salvo: {filename}")

                    else:
                        # Para SIH (Mensal)
                        # Assinatura correta: download(states, years, months, groups, data_dir)
                        for mes in range(1, 13):
                            mes_str = f"{mes:02d}"
                            parquet_set = config['func'](
                                states=estado,
                                years=ano,
                                months=mes,
                                groups=config['groups']
                            )

                            # A função retorna um ParquetSet, use to_dataframe() diretamente
                            if parquet_set:
                                df = parquet_set.to_dataframe()

                                if not df.empty:
                                    filename = f"{sistema}_{estado}_{ano}_{mes_str}.parquet"
                                    file_full_path = os.path.join(caminho_destino, filename)
                                    df.to_parquet(file_full_path, index=False)
                        print(f"Salvo: Todos os meses do {sistema} para {estado} em {ano}")

                except Exception as e:
                    print(f"Erro ao processar {sistema} para {estado} {ano}: {e}")


# 3. Execução do Script
# Testando com São Paulo para o ano de 2022
meus_estados = ['SP']
meus_anos = [2021]

if __name__ == "__main__":
    baixar_e_salvar_dados(meus_estados, meus_anos)