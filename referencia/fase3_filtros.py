
# ============================================================================
# FASE 3: DEFINIÇÃO DE CRITÉRIOS TEMÁTICOS BASEADOS NA INTENÇÃO DE PESQUISA
# ============================================================================

print("\n" + "="*80)
print("[FASE 3] FILTRAGEM TEMÁTICA - DEFINIÇÃO DE CRITÉRIOS DE ADERÊNCIA")
print("="*80 + "\n")

# Critérios extraídos da sua dissertação (arquivo 8 e 12)
print("CONTEXTO DA DISSERTAÇÃO (Daiane Wan-Dall Splitter da Silva):")
print("  Objetivo: Modelo preditivo para previsão de enchentes em comunidades costeiras")
print("  Foco: Santa Catarina, Brasil")
print("  Dados de entrada: Satélites, sensores, registros históricos de enchentes")
print("  Algoritmos esperados: LSTM, RNN, redes multicamadas, ensemble methods")
print("  Saídas: Previsão de risco, mapas de suscetibilidade, early warning")
print("\n")

# Definição de termos-chave por categoria
keywords_core = {
    'flood_prediction': [
        'flood prediction', 'flood forecast', 'flood early warning',
        'flood forecasting', 'inundation prediction', 'flood susceptibility',
        'flood risk', 'flood modeling', 'flood hazard', 'flooding',
        'enchentes', 'previsão de enchentes', 'previsão de inundações',
        'risco de inundação', 'modelagem de inundações', 'inundação urbana',
        'alerta de cheias', 'mapeamento de risco de cheias'
    ],
    'ai_ml_methods': [
        'machine learning', 'deep learning', 'lstm', 'rnn', 'neural network',
        'random forest', 'ensemble', 'support vector machine', 'xgboost',
        'artificial intelligence', 'data-driven', 'convolutional', 'cnn',
        'artificial neural', 'gradient boosting', 'supervised learning',
        'aprendizado de máquina', 'aprendizado profundo', 'rede neural',
        'inteligência artificial'
    ],
    'hydrological_data': [
        'rainfall', 'precipitation', 'water level', 'streamflow', 'discharge',
        'river', 'hydrological', 'hydrologic', 'basin', 'watershed',
        'gauge', 'stream', 'flow rate', 'inundation depth', 'inundation extent',
        'chuva', 'precipitação', 'nível de água', 'vazão', 'hidrológico'
    ],
    'geospatial_data': [
        'satellite', 'remote sensing', 'dem', 'digital elevation', 'landsat',
        'sentinel', 'geospatial', 'spatial', 'gis', 'raster', 'urban',
        'land cover', 'land use', 'lulc', 'ndvi', 'radar',
        'imagem satélite', 'sensoriamento remoto', 'terreno', 'mapa'
    ]
}

# Critérios de exclusão
keywords_exclude = [
    'flood myth', 'flood geology', 'flood insurance', 'flood psychology',
    'flood relief', 'flood control structure', 'dam', 'dike', 'levee',
    'flood insurance rate', 'flood mitigation infrastructure', 'green infrastructure',
    'semantic flooding', 'buffer overflow', 'network flooding'
]

print("TERMOS-CHAVE POR CATEGORIA:\n")
for cat, terms in keywords_core.items():
    print(f"  {cat.upper()}: {len(terms)} termos")
    print(f"    Exemplos: {', '.join(terms[:5])}...")

print(f"\n  TERMOS DE EXCLUSÃO: {len(keywords_exclude)} termos")
print(f"    Exemplos: {', '.join(keywords_exclude[:5])}...")

# Função de scoring temático
def check_keyword_presence(text, keywords_list, match_type='any'):
    """
    Verifica presença de palavras-chave em um texto
    match_type: 'any' (pelo menos 1), 'multiple' (múltiplas)
    """
    if pd.isna(text) or text == '':
        return 0
    
    text_lower = str(text).lower()
    matches = 0
    for kw in keywords_list:
        if kw.lower() in text_lower:
            matches += 1
    
    if match_type == 'any':
        return 1 if matches >= 1 else 0
    elif match_type == 'multiple':
        return 1 if matches >= 2 else 0
    return matches

def check_exclusion(text, keywords_exclude):
    """
    Verifica se o texto contém termos de exclusão
    """
    if pd.isna(text) or text == '':
        return False
    
    text_lower = str(text).lower()
    for kw in keywords_exclude:
        if kw.lower() in text_lower:
            return True
    return False

print("\n" + "="*80)
print("[FASE 3a] APLICAÇÃO DE FILTROS TEMÁTICOS")
print("="*80 + "\n")

# Criar campos de scoring temático
df_consolidated['flood_pred_score'] = df_consolidated.apply(
    lambda row: check_keyword_presence(
        str(row['title']) + ' ' + str(row['abstract']) + ' ' + str(row['keywords']),
        keywords_core['flood_prediction'],
        'any'
    ), axis=1
)

df_consolidated['ai_ml_score'] = df_consolidated.apply(
    lambda row: check_keyword_presence(
        str(row['title']) + ' ' + str(row['abstract']) + ' ' + str(row['keywords']),
        keywords_core['ai_ml_methods'],
        'any'
    ), axis=1
)

df_consolidated['hydro_score'] = df_consolidated.apply(
    lambda row: check_keyword_presence(
        str(row['abstract']) + ' ' + str(row['keywords']),
        keywords_core['hydrological_data'],
        'any'
    ), axis=1
)

df_consolidated['geospatial_score'] = df_consolidated.apply(
    lambda row: check_keyword_presence(
        str(row['abstract']) + ' ' + str(row['keywords']),
        keywords_core['geospatial_data'],
        'any'
    ), axis=1
)

df_consolidated['is_excluded'] = df_consolidated.apply(
    lambda row: check_exclusion(
        str(row['title']) + ' ' + str(row['abstract']),
        keywords_exclude
    ), axis=1
)

print("✓ Scores temáticos calculados para todos os artigos\n")

# Calcular composição temática
print("DISTRIBUIÇÃO DE SCORES TEMÁTICOS:\n")
print(f"  Artigos com 'flood prediction': {df_consolidated['flood_pred_score'].sum()} ({df_consolidated['flood_pred_score'].sum()/len(df_consolidated)*100:.1f}%)")
print(f"  Artigos com 'AI/ML': {df_consolidated['ai_ml_score'].sum()} ({df_consolidated['ai_ml_score'].sum()/len(df_consolidated)*100:.1f}%)")
print(f"  Artigos com dados 'hidrológicos': {df_consolidated['hydro_score'].sum()} ({df_consolidated['hydro_score'].sum()/len(df_consolidated)*100:.1f}%)")
print(f"  Artigos com dados 'geoespaciais': {df_consolidated['geospatial_score'].sum()} ({df_consolidated['geospatial_score'].sum()/len(df_consolidated)*100:.1f}%)")
print(f"  Artigos EXCLUÍDOS por palavras negativas: {df_consolidated['is_excluded'].sum()}")

# CRITÉRIO 1: Núcleo obrigatório
print("\n" + "="*80)
print("[FILTRO 1] NÚCLEO OBRIGATÓRIO (Flood Prediction + AI/ML + NOT Excluded)")
print("="*80 + "\n")

df_core = df_consolidated[
    (df_consolidated['flood_pred_score'] == 1) &
    (df_consolidated['ai_ml_score'] == 1) &
    (df_consolidated['is_excluded'] == False)
].copy()

print(f"Artigos no NÚCLEO OBRIGATÓRIO: {len(df_core)} ({len(df_core)/len(df_consolidated)*100:.1f}%)\n")

# CRITÉRIO 2: Núcleo expandido (permite um OU outro em dados)
print("="*80)
print("[FILTRO 2] NÚCLEO EXPANDIDO (FP + AI/ML + (Hydro OR Geospatial) + NOT Excluded)")
print("="*80 + "\n")

df_expanded = df_consolidated[
    (df_consolidated['flood_pred_score'] == 1) &
    (df_consolidated['ai_ml_score'] == 1) &
    ((df_consolidated['hydro_score'] == 1) | (df_consolidated['geospatial_score'] == 1)) &
    (df_consolidated['is_excluded'] == False)
].copy()

print(f"Artigos no NÚCLEO EXPANDIDO: {len(df_expanded)} ({len(df_expanded)/len(df_consolidated)*100:.1f}%)\n")

# CRITÉRIO 3: Periférico (apenas FP + AI/ML, sem necessidade de dados específicos)
print("="*80)
print("[FILTRO 3] PERIFÉRICO (FP + AI/ML + NOT Excluded, sem restrição de dados)")
print("="*80 + "\n")

df_peripheral = df_consolidated[
    (df_consolidated['flood_pred_score'] == 1) &
    (df_consolidated['ai_ml_score'] == 1) &
    (df_consolidated['is_excluded'] == False)
].copy()

print(f"Artigos no PERIFÉRICO: {len(df_peripheral)} ({len(df_peripheral)/len(df_consolidated)*100:.1f}%)\n")

print("="*80)
print("RESUMO DE FILTROS TEMÁTICOS")
print("="*80)
print(f"  Base original....................: {len(df_consolidated):>5} artigos")
print(f"  - Núcleo obrigatório (criterioso): {len(df_core):>5} artigos ({len(df_core)/len(df_consolidated)*100:.1f}%)")
print(f"  - Núcleo expandido (moderado)....: {len(df_expanded):>5} artigos ({len(df_expanded)/len(df_consolidated)*100:.1f}%)")
print(f"  - Periférico (liberal)...........: {len(df_peripheral):>5} artigos ({len(df_peripheral)/len(df_consolidated)*100:.1f}%)")
print("="*80)