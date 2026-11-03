
# ============================================================================
# FASE 4: CÁLCULO DE SCORES DE RELEVÂNCIA COM EQUAÇÕES EXPLÍCITAS
# ============================================================================

print("\n" + "="*80)
print("[FASE 4] CÁLCULO DE SCORES DE RELEVÂNCIA BIBLIOMÉTRICOS")
print("="*80 + "\n")

# Usar o Núcleo Expandido como ponto de partida (balanço entre rigor e viabilidade)
df_analysis = df_expanded.copy()

print(f"Base para análise de score: {len(df_analysis)} artigos\n")

print("="*80)
print("COMPONENTES DO SCORE DE RELEVÂNCIA")
print("="*80 + "\n")

# 1. SCORE DE CITAÇÕES NORMALIZADO (C*)
print("1. SCORE DE CITAÇÕES NORMALIZADAS (C*)\n")

max_citations = df_analysis['citations'].max()
min_citations = df_analysis['citations'].min()

print(f"   Citações - Min: {min_citations}, Max: {max_citations}, Média: {df_analysis['citations'].mean():.1f}")
print(f"\n   Equação: C*_i = (C_i - min) / (max - min)")
print(f"   Onde C_i = número de citações do artigo i\n")

df_analysis['C_norm'] = (df_analysis['citations'] - min_citations) / (max_citations - min_citations) if max_citations > min_citations else 0
df_analysis['C_norm'] = df_analysis['C_norm'].fillna(0)

print(f"   ✓ C* calculado (intervalo: 0.0 a 1.0)")

# 2. SCORE DE RECÊNCIA (R*)
print("\n2. SCORE DE RECÊNCIA (R*)\n")

max_year = df_analysis['year'].max()
min_year = df_analysis['year'][df_analysis['year'].notna()].min()

print(f"   Período - Min: {min_year:.0f}, Max: {max_year:.0f}")
print(f"\n   Equação: R*_i = (Y_i - min_year) / (max_year - min_year)")
print(f"   Onde Y_i = ano de publicação do artigo i\n")

# Tratar anos missing
df_analysis['R_norm'] = df_analysis['year'].apply(
    lambda y: (y - min_year) / (max_year - min_year) if pd.notna(y) and y >= min_year else 0
)

print(f"   ✓ R* calculado (intervalo: 0.0 a 1.0)")

# 3. SCORE DE ADERÊNCIA TEMÁTICA (T*)
print("\n3. SCORE DE ADERÊNCIA TEMÁTICA (T*)\n")

print("   Categorias:")
print("   - Categoria A (máxima aderência): título + abstract + keywords com termos flood prediction E AI/ML")
print("   - Categoria B (aderência moderada): título ou abstract com termos flood prediction E AI/ML")
print("   - Categoria C (aderência baixa): apenas uma categoria de busca presente\n")

def classify_thematic_adherence(row):
    """
    Classifica a aderência temática em 3 níveis
    """
    # Montar texto para cada campo
    title_abstract_kw = str(row['title']) + ' ' + str(row['abstract']) + ' ' + str(row['keywords'])
    title = str(row['title'])
    
    # Contar ocorrências em título vs resto
    flood_in_title = check_keyword_presence(title, keywords_core['flood_prediction'])
    ai_in_title = check_keyword_presence(title, keywords_core['ai_ml_methods'])
    
    flood_in_content = check_keyword_presence(title_abstract_kw, keywords_core['flood_prediction'])
    ai_in_content = check_keyword_presence(title_abstract_kw, keywords_core['ai_ml_methods'])
    
    # Categoria A: máxima (flood + AI no título ou em multiple campos)
    if (flood_in_title and ai_in_title):
        return 1.0
    # Categoria B: moderada (flood + AI em abstract/keywords)
    elif (flood_in_content and ai_in_content):
        return 0.7
    # Categoria C: baixa (um dos dois)
    else:
        return 0.4

df_analysis['T_score'] = df_analysis.apply(classify_thematic_adherence, axis=1)

print(f"   Distribuição de aderência temática:")
print(f"   - Categoria A (T*=1.0): {(df_analysis['T_score'] == 1.0).sum()} artigos ({(df_analysis['T_score'] == 1.0).sum()/len(df_analysis)*100:.1f}%)")
print(f"   - Categoria B (T*=0.7): {(df_analysis['T_score'] == 0.7).sum()} artigos ({(df_analysis['T_score'] == 0.7).sum()/len(df_analysis)*100:.1f}%)")
print(f"   - Categoria C (T*=0.4): {(df_analysis['T_score'] == 0.4).sum()} artigos ({(df_analysis['T_score'] == 0.4).sum()/len(df_analysis)*100:.1f}%)\n")

print(f"   ✓ T* calculado (intervalo: 0.4 a 1.0)")

# 4. SCORE DE ADERÊNCIA AOS DADOS/MÉTODO/RESULTADO (A*)
print("\n4. SCORE DE ADERÊNCIA AOS DADOS/MÉTODO/RESULTADO (A*)\n")

print("   Componentes:")
print("   - Input (I): presença de dados hidrológicos OU geoespaciais")
print("   - Method (M): presença de termos de ML/DL explícitos")
print("   - Output (O): previsão/forecasting/early warning/mapping")
print("   - Context (C): aplicação em inundações urbanas ou costeiras\n")

print("   Equação: A*_i = (I_i + M_i + O_i + C_i) / 4")
print("   Onde cada termo ∈ {0.0, 0.5, 1.0}\n")

# Input scoring
input_keywords = keywords_core['hydrological_data'] + keywords_core['geospatial_data']
df_analysis['input_score'] = df_analysis.apply(
    lambda row: (1.0 if check_keyword_presence(str(row['abstract']) + ' ' + str(row['keywords']), input_keywords) 
                 else 0.0), axis=1
)

# Method scoring (must have explicit ML/DL terms)
ml_specific = ['lstm', 'rnn', 'cnn', 'deep learning', 'neural network', 'machine learning', 
               'ensemble', 'random forest', 'support vector', 'xgboost', 'aprendizado de máquina',
               'rede neural', 'aprendizado profundo']
df_analysis['method_score'] = df_analysis.apply(
    lambda row: (1.0 if check_keyword_presence(str(row['abstract']) + ' ' + str(row['title']), ml_specific) 
                 else 0.5), axis=1
)

# Output scoring (prediction, forecasting, early warning, mapping)
output_keywords = ['prediction', 'forecast', 'early warning', 'risk mapping', 'susceptibility', 
                   'mapping', 'previsão', 'mapeamento', 'alerta']
df_analysis['output_score'] = df_analysis.apply(
    lambda row: (1.0 if check_keyword_presence(str(row['title']) + ' ' + str(row['abstract']), output_keywords) 
                 else 0.5), axis=1
)

# Context scoring (urban/coastal/basin-specific)
context_keywords = ['urban', 'coastal', 'river', 'basin', 'watershed', 'city', 'communities',
                    'urbano', 'costeiro', 'comunidades', 'rio']
df_analysis['context_score'] = df_analysis.apply(
    lambda row: (1.0 if check_keyword_presence(str(row['abstract']) + ' ' + str(row['keywords']), context_keywords) 
                 else 0.5), axis=1
)

df_analysis['A_score'] = (df_analysis['input_score'] + df_analysis['method_score'] + 
                           df_analysis['output_score'] + df_analysis['context_score']) / 4

print(f"   Distribuição de aderência a dados/método/resultado:")
print(f"   - A* ≥ 0.9: {(df_analysis['A_score'] >= 0.9).sum()} artigos ({(df_analysis['A_score'] >= 0.9).sum()/len(df_analysis)*100:.1f}%)")
print(f"   - 0.7 ≤ A* < 0.9: {((df_analysis['A_score'] >= 0.7) & (df_analysis['A_score'] < 0.9)).sum()} artigos")
print(f"   - 0.5 ≤ A* < 0.7: {((df_analysis['A_score'] >= 0.5) & (df_analysis['A_score'] < 0.7)).sum()} artigos\n")

print(f"   ✓ A* calculado (intervalo: 0.5 a 1.0)")

# 5. CÁLCULO DO SCORE FINAL
print("\n" + "="*80)
print("5. SCORE DE RELEVÂNCIA FINAL")
print("="*80 + "\n")

w1, w2, w3, w4 = 0.35, 0.20, 0.30, 0.15  # pesos

print(f"Equação geral:")
print(f"\n   Score_i = w1·C*_i + w2·R*_i + w3·T*_i + w4·A*_i\n")
print(f"Onde:")
print(f"   C*_i = Citações normalizadas (peso w1 = {w1})")
print(f"   R*_i = Recência normalizada (peso w2 = {w2})")
print(f"   T*_i = Aderência temática (peso w3 = {w3})")
print(f"   A*_i = Aderência dados/método/resultado (peso w4 = {w4})")
print(f"   Total de pesos: {w1 + w2 + w3 + w4}\n")

df_analysis['score_final'] = (w1 * df_analysis['C_norm'] + 
                               w2 * df_analysis['R_norm'] + 
                               w3 * df_analysis['T_score'] + 
                               w4 * df_analysis['A_score'])

# Normalizar score final para intervalo 0-100
min_score = df_analysis['score_final'].min()
max_score = df_analysis['score_final'].max()
df_analysis['score_final_100'] = ((df_analysis['score_final'] - min_score) / (max_score - min_score) * 100).round(2)

print(f"✓ Score final calculado")
print(f"\nEstatísticas do Score Final (0-100):")
print(f"   Mínimo: {df_analysis['score_final_100'].min():.2f}")
print(f"   Máximo: {df_analysis['score_final_100'].max():.2f}")
print(f"   Média: {df_analysis['score_final_100'].mean():.2f}")
print(f"   Mediana: {df_analysis['score_final_100'].median():.2f}")
print(f"   Desvio padrão: {df_analysis['score_final_100'].std():.2f}")