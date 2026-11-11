
# ============================================================================
# FASE 2: NORMALIZAÇÃO E PREPARAÇÃO DE DADOS
# ============================================================================

print("\n" + "="*80)
print("[FASE 2] NORMALIZAÇÃO E HARMONIZAÇÃO DE CAMPOS")
print("="*80 + "\n")

# Função para inspecionar campos disponíveis
def inspect_dataframe(df, name, nrows=3):
    print(f"\n{name}")
    print(f"  Dimensões: {df.shape}")
    if len(df) > 0:
        print(f"  Colunas: {list(df.columns[:10])}...")
    return df

# Inspeção breve
lens_en = inspect_dataframe(lens_en, "Lens (EN)")
scopus_all = inspect_dataframe(scopus_all, "Scopus (Sem Filtro)")
ieee = inspect_dataframe(ieee, "IEEE")
scielo_en = inspect_dataframe(scielo_en, "SciELO (EN)")

print("\n" + "="*80)
print("[FASE 2a] MAPEAMENTO DE COLUNAS COMUNS")
print("="*80 + "\n")

# Mapeamento de campos-chave entre bases
field_mapping = {
    'lens': {
        'title': 'Title',
        'year': 'Publication Year',
        'abstract': 'Abstract',
        'keywords': 'Keywords',
        'citations': 'Citing Works Count',
        'doi': 'DOI',
        'source': 'Source Title',
        'field': 'Fields of Study'
    },
    'scopus': {
        'title': 'Title',
        'year': 'Year',
        'abstract': 'Abstract',
        'keywords': 'Keywords',
        'citations': 'Cited by',
        'doi': 'DOI',
        'source': 'Source title',
        'field': 'Document Type'
    },
    'ieee': {
        'title': 'Title',
        'year': 'Publication Year',
        'abstract': 'Abstract',
        'keywords': 'Keywords',
        'citations': 'Citations',
        'doi': 'DOI',
        'source': 'Source Title',
        'field': 'Content Type'
    },
    'scielo': {
        'title': 'Title',
        'year': 'Year',
        'abstract': 'Abstract',
        'keywords': 'Keywords',
        'citations': None,
        'doi': 'DOI',
        'source': 'Source',
        'field': 'Document Type'
    }
}

print("✓ Mapeamento de campos definido para 4 bases principais")

# Função para normalizar e consolidar dados
def normalize_database(df, base_name, mapping, db_type='lens'):
    """
    Normaliza um dataframe usando o mapeamento específico
    """
    if len(df) == 0:
        return pd.DataFrame()
    
    normalized = pd.DataFrame()
    normalized['source_db'] = base_name
    normalized['db_type'] = db_type
    
    # Título
    if mapping.get('title') in df.columns:
        normalized['title'] = df[mapping['title']].fillna('Unknown')
    else:
        normalized['title'] = 'Unknown'
    
    # Ano
    if mapping.get('year') in df.columns:
        try:
            normalized['year'] = pd.to_numeric(df[mapping['year']], errors='coerce').astype('Int64')
        except:
            normalized['year'] = None
    else:
        normalized['year'] = None
    
    # Abstract
    if mapping.get('abstract') in df.columns:
        normalized['abstract'] = df[mapping['abstract']].fillna('')
    else:
        normalized['abstract'] = ''
    
    # Keywords
    if mapping.get('keywords') in df.columns:
        normalized['keywords'] = df[mapping['keywords']].fillna('')
    else:
        normalized['keywords'] = ''
    
    # Citações
    if mapping.get('citations') and mapping['citations'] in df.columns:
        try:
            normalized['citations'] = pd.to_numeric(df[mapping['citations']], errors='coerce').fillna(0).astype(int)
        except:
            normalized['citations'] = 0
    else:
        normalized['citations'] = 0
    
    # DOI
    if mapping.get('doi') in df.columns:
        normalized['doi'] = df[mapping['doi']].fillna('')
    else:
        normalized['doi'] = ''
    
    # Fonte
    if mapping.get('source') in df.columns:
        normalized['source'] = df[mapping['source']].fillna('Unknown')
    else:
        normalized['source'] = 'Unknown'
    
    return normalized

print("\n✓ Função de normalização definida")

# Normalizar bases principais
print("\nNormalizando bases...\n")

norm_lens_en = normalize_database(lens_en, 'Lens (EN)', field_mapping['lens'], 'lens')
print(f"  Lens (EN) normalizada: {len(norm_lens_en)} registros")

norm_lens_pt = normalize_database(lens_pt, 'Lens (PT)', field_mapping['lens'], 'lens')
print(f"  Lens (PT) normalizada: {len(norm_lens_pt)} registros")

norm_scopus_all = normalize_database(scopus_all, 'Scopus (Sem Filtro)', field_mapping['scopus'], 'scopus')
print(f"  Scopus (Sem Filtro) normalizada: {len(norm_scopus_all)} registros")

norm_scopus_filtered = normalize_database(scopus_filtered, 'Scopus (Com Filtro)', field_mapping['scopus'], 'scopus')
print(f"  Scopus (Com Filtro) normalizada: {len(norm_scopus_filtered)} registros")

norm_scopus_pt = normalize_database(scopus_pt, 'Scopus (PT)', field_mapping['scopus'], 'scopus')
print(f"  Scopus (PT) normalizada: {len(norm_scopus_pt)} registros")

norm_ieee = normalize_database(ieee, 'IEEE Xplore', field_mapping['ieee'], 'ieee')
print(f"  IEEE Xplore normalizada: {len(norm_ieee)} registros")

norm_scielo_en = normalize_database(scielo_en, 'SciELO (EN)', field_mapping['scielo'], 'scielo')
print(f"  SciELO (EN) normalizada: {len(norm_scielo_en)} registros")

norm_scielo_pt = normalize_database(scielo_pt, 'SciELO (PT)', field_mapping['scielo'], 'scielo')
print(f"  SciELO (PT) normalizada: {len(norm_scielo_pt)} registros")

# Consolidar em uma base única, removendo duplicatas
print("\n" + "="*80)
print("[FASE 2b] CONSOLIDAÇÃO E DEDUPLICAÇÃO")
print("="*80 + "\n")

all_dfs = [
    norm_lens_en, norm_lens_pt,
    norm_scopus_all, norm_scopus_filtered, norm_scopus_pt,
    norm_ieee,
    norm_scielo_en, norm_scielo_pt
]

# Remover DataFrames vazios
all_dfs = [df for df in all_dfs if len(df) > 0]

# Consolidar
df_consolidated = pd.concat(all_dfs, ignore_index=True)

print(f"Registros antes de deduplicação: {len(df_consolidated)}")

# Deduplicar por DOI (se disponível) e depois por título
df_consolidated['title_normalized'] = df_consolidated['title'].str.lower().str.strip()

# Primeiro, remover por DOI
df_consolidated = df_consolidated[df_consolidated['doi'] != ''].drop_duplicates(subset=['doi'], keep='first')
print(f"Após remover DOIs duplicados: {len(df_consolidated)}")

# Depois, remover por título (use case-insensitive)
df_consolidated = df_consolidated.drop_duplicates(subset=['title_normalized'], keep='first')
print(f"Após remover títulos duplicados: {len(df_consolidated)}")

print(f"\n✓ Base consolidada: {len(df_consolidated)} artigos únicos")

# Resumo estatístico básico
print("\n" + "="*80)
print("RESUMO DESCRITIVO DA BASE CONSOLIDADA")
print("="*80)
print(f"\nArtigos por fonte:")
print(df_consolidated['source_db'].value_counts().to_string())
print(f"\nPeríodo de publicação: {df_consolidated['year'].min():.0f} - {df_consolidated['year'].max():.0f}")
print(f"Anos com dados: {df_consolidated['year'].notna().sum()}")
print(f"Artigos com Abstract: {(df_consolidated['abstract'] != '').sum()}")
print(f"Artigos com Palavras-chave: {(df_consolidated['keywords'] != '').sum()}")
print(f"Artigos com DOI: {(df_consolidated['doi'] != '').sum()}")
print(f"Citações (média): {df_consolidated['citations'].mean():.2f}")
print(f"Citações (mediana): {df_consolidated['citations'].median():.0f}")