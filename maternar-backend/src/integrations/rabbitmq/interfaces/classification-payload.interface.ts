export interface IClassificationPayload {
  nu_peso: number;
  nu_altura: number;
  nu_imc_pre_gestacional: number;
  raca_cor: number;
  escolaridade: number;
  cod_municipio: string;
  flag_anti_hiv: number;
}

export interface IClassificacaoRecomendacao {
  categoria: string;
  texto: string;
}

export interface IClassificacaoMetricas {
  nu_imc_calculado: number;
  ganho_imc: number;
  estado_nutricional: string;
  cnes_hospitais_municipio: number;
}

export interface IClassificationResponse {
  cluster_id: number;
  cluster_nome: string;
  cluster_nome_app: string;
  nivel_risco: string;
  cor_hex: string;
  recomendacoes: IClassificacaoRecomendacao[];
  metricas: IClassificacaoMetricas;
  correlation_id: string;
}
