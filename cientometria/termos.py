"""Listas de termos do método (idênticas às do script original de jan/2026).

Atenção: o casamento é por TRECHO DE TEXTO sem distinção de caixa. Termos curtos
('dem', 'gis', 'rnn', 'cnn', 'dam') casam dentro de outras palavras. Isso é
uma característica do método original, mantida no modo 'original' e discutida
no capítulo (ver Config.exclusao_palavra_inteira).
"""

NUCLEO = {
    "flood_prediction": [
        "flood prediction", "flood forecast", "flood early warning",
        "flood forecasting", "inundation prediction", "flood susceptibility",
        "flood risk", "flood modeling", "flood hazard", "flooding",
        "enchentes", "previsão de enchentes", "previsão de inundações",
        "risco de inundação", "modelagem de inundações", "inundação urbana",
        "alerta de cheias", "mapeamento de risco de cheias",
    ],
    "ai_ml_methods": [
        "machine learning", "deep learning", "lstm", "rnn", "neural network",
        "random forest", "ensemble", "support vector machine", "xgboost",
        "artificial intelligence", "data-driven", "convolutional", "cnn",
        "artificial neural", "gradient boosting", "supervised learning",
        "aprendizado de máquina", "aprendizado profundo", "rede neural",
        "inteligência artificial",
    ],
    "hydrological_data": [
        "rainfall", "precipitation", "water level", "streamflow", "discharge",
        "river", "hydrological", "hydrologic", "basin", "watershed",
        "gauge", "stream", "flow rate", "inundation depth", "inundation extent",
        "chuva", "precipitação", "nível de água", "vazão", "hidrológico",
    ],
    "geospatial_data": [
        "satellite", "remote sensing", "dem", "digital elevation", "landsat",
        "sentinel", "geospatial", "spatial", "gis", "raster", "urban",
        "land cover", "land use", "lulc", "ndvi", "radar",
        "imagem satélite", "sensoriamento remoto", "terreno", "mapa",
    ],
}

EXCLUSAO = [
    "flood myth", "flood geology", "flood insurance", "flood psychology",
    "flood relief", "flood control structure", "dam", "dike", "levee",
    "flood insurance rate", "flood mitigation infrastructure", "green infrastructure",
    "semantic flooding", "buffer overflow", "network flooding",
]

# Termos usados apenas no escore A* (método, resultado, contexto)
ML_ESPECIFICO = [
    "lstm", "rnn", "cnn", "deep learning", "neural network", "machine learning",
    "ensemble", "random forest", "support vector", "xgboost", "aprendizado de máquina",
    "rede neural", "aprendizado profundo",
]
SAIDA = ["prediction", "forecast", "early warning", "risk mapping", "susceptibility",
         "mapping", "previsão", "mapeamento", "alerta"]
CONTEXTO = ["urban", "coastal", "river", "basin", "watershed", "city", "communities",
            "urbano", "costeiro", "comunidades", "rio"]

# Termos que, no modo "variante"/"corrigido", são casados como palavra inteira
EXCLUSAO_CURTA = ("dam", "dike", "levee")
