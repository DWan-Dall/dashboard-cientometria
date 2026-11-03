
# Corrigir o erro de sintaxe na ordenação

print("\n" + "="*80)
print("[FASE 5] FÁCIAS DE PRIORIDADE E CORTES BIBLIOGRÁFICOS")
print("="*80 + "\n")

# Definir limites de corte usando percentis
percentis = df_analysis['score_final_100'].quantile([0.25, 0.5, 0.75, 0.90])

print("PERCENTIS DE DISTRIBUIÇÃO DE SCORES:\n")
for p, val in percentis.items():
    print(f"   {p*100:.0f}º percentil: {val:.2f}")

# Definir fácias
CORTE_NUCLEOA = 70
CORTE_NUCLEOB = 50
CORTE_PERIFERICA = 30

print("\n" + "="*80)
print("DEFINIÇÃO DE FÁCIAS")
print("="*80 + "\n")

df_analysis['fascia'] = 'Descarte'

# Núcleo A: top tier
df_analysis.loc[(df_analysis['score_final_100'] >= CORTE_NUCLEOA), 'fascia'] = 'Núcleo A'

# Núcleo B: medium-high
df_analysis.loc[(df_analysis['score_final_100'] >= CORTE_NUCLEOB) & 
                (df_analysis['score_final_100'] < CORTE_NUCLEOA), 'fascia'] = 'Núcleo B'

# Periférico
df_analysis.loc[(df_analysis['score_final_100'] >= CORTE_PERIFERICA) & 
                (df_analysis['score_final_100'] < CORTE_NUCLEOB), 'fascia'] = 'Periférico'

print(f"FÁCIAS DEFINIDAS COM CRITÉRIOS:\n")
print(f"1. NÚCLEO A (Leitura Detalhada - PRIORITÁRIO)")
print(f"   Critério: Score ≥ {CORTE_NUCLEOA}")
print(f"   Justificativa: Artigos com altíssima aderência temática, relevância e citações")
print(f"   Expectativa: ~{(df_analysis['fascia'] == 'Núcleo A').sum()} artigos\n")

print(f"2. NÚCLEO B (Leitura Seletiva - IMPORTANTE)")
print(f"   Critério: {CORTE_NUCLEOB} ≤ Score < {CORTE_NUCLEOA}")
print(f"   Justificativa: Artigos de boa qualidade, com boa aderência mas menos influentes")
print(f"   Expectativa: ~{(df_analysis['fascia'] == 'Núcleo B').sum()} artigos\n")

print(f"3. PERIFÉRICO (Leitura Opcional - COMPLEMENTAR)")
print(f"   Critério: {CORTE_PERIFERICA} ≤ Score < {CORTE_NUCLEOB}")
print(f"   Justificativa: Artigos relevantes mas com fatores limitantes")
print(f"   Expectativa: ~{(df_analysis['fascia'] == 'Periférico').sum()} artigos\n")

print(f"4. DESCARTE (Não Recomendado - EXCLUIR)")
print(f"   Critério: Score < {CORTE_PERIFERICA}")
print(f"   Justificativa: Baixa relevância, foco marginal")
print(f"   Expectativa: ~{(df_analysis['fascia'] == 'Descarte').sum()} artigos\n")

# Resumo de distribuição
print("="*80)
print("RESUMO DE DISTRIBUIÇÃO POR FÁCIA")
print("="*80 + "\n")

fascias_order = ['Núcleo A', 'Núcleo B', 'Periférico', 'Descarte']

for fascia in fascias_order:
    count = (df_analysis['fascia'] == fascia).sum()
    pct = count / len(df_analysis) * 100
    print(f"  {fascia:.<30} {count:>5} artigos ({pct:>5.1f}%)")

print(f"  {'TOTAL':.<30} {len(df_analysis):>5} artigos")

# Análise detalhada por fácia
print("\n" + "="*80)
print("ANÁLISE DESCRITIVA POR FÁCIA")
print("="*80 + "\n")

for fascia in ['Núcleo A', 'Núcleo B', 'Periférico']:
    subset = df_analysis[df_analysis['fascia'] == fascia]
    if len(subset) > 0:
        print(f"\n{fascia.upper()}")
        print(f"  Quantidade: {len(subset)} artigos")
        print(f"  Score final - Mín: {subset['score_final_100'].min():.1f}, Máx: {subset['score_final_100'].max():.1f}, "
              f"Média: {subset['score_final_100'].mean():.1f}")
        print(f"  Citações - Mín: {subset['citations'].min():.0f}, Máx: {subset['citations'].max():.0f}, "
              f"Média: {subset['citations'].mean():.1f}")
        
        recent_years = subset[subset['year'] >= 2020].shape[0]
        print(f"  Artigos publicados após 2020: {recent_years} ({recent_years/len(subset)*100:.1f}%)")
        
        with_abstract = (subset['abstract'] != '').sum()
        print(f"  Artigos com abstract: {with_abstract} ({with_abstract/len(subset)*100:.1f}%)")

# Estatísticas de pesos por fácia
print("\n" + "="*80)
print("CONTRIBUIÇÃO MÉDIA DOS COMPONENTES DO SCORE POR FÁCIA")
print("="*80 + "\n")

for fascia in ['Núcleo A', 'Núcleo B', 'Periférico']:
    subset = df_analysis[df_analysis['fascia'] == fascia]
    if len(subset) > 0:
        print(f"\n{fascia.upper()}")
        contrib_c = (w1 * subset['C_norm'].mean())
        contrib_r = (w2 * subset['R_norm'].mean())
        contrib_t = (w3 * subset['T_score'].mean())
        contrib_a = (w4 * subset['A_score'].mean())
        
        print(f"  Contribuição C* (Citações):     {contrib_c:.3f} ({contrib_c*100:.1f}% do score)")
        print(f"  Contribuição R* (Recência):     {contrib_r:.3f} ({contrib_r*100:.1f}% do score)")
        print(f"  Contribuição T* (Temática):     {contrib_t:.3f} ({contrib_t*100:.1f}% do score)")
        print(f"  Contribuição A* (Dados/Método): {contrib_a:.3f} ({contrib_a*100:.1f}% do score)")
        print(f"  {'Total:':.<20} {contrib_c + contrib_r + contrib_t + contrib_a:.3f}")