# Strings de busca — EN/PT — por base

Período sugerido: 2000–2025 (ajuste conforme necessário).  
Tipos de documento: Articles, Reviews (incluir Conference Papers se desejar).

---

## SCOPUS (campos: TITLE-ABS-KEY)
Use `TITLE-ABS-KEY(...)` e filtros de ano/tipo na interface.

### Global (costeira)
```
TITLE-ABS-KEY(
 (flood* OR inundation* OR "flash flood*" OR "urban flooding")
 AND ("machine learning" OR "deep learning" OR "neural network*" OR LSTM OR "random forest" OR "gradient boosting")
 AND (coast* OR "coastal zone*" OR shoreline OR estuary OR "storm surge" OR tide OR "sea level")
)
AND (PUBYEAR > 1999 AND PUBYEAR < 2026)
AND (LIMIT-TO(DOCTYPE, "ar") OR LIMIT-TO(DOCTYPE, "re"))
```

### Brasil/SC reforço (opcional adicionar ao bloco acima)
```
AND (Brazil OR "Santa Catarina" OR Itajaí OR Florianópolis OR "Itajai-Açu" OR "Vale do Itajaí")
```

### Sem recorte costeiro (capturar métodos gerais e filtrar depois)
```
TITLE-ABS-KEY(
 (flood* OR inundation* OR "flash flood*" OR "river discharge" OR "streamflow")
 AND ("machine learning" OR "deep learning" OR "neural network*" OR LSTM OR "random forest" OR "gradient boosting" OR XGBoost)
)
AND (PUBYEAR > 1999 AND PUBYEAR < 2026)
AND (LIMIT-TO(DOCTYPE, "ar") OR LIMIT-TO(DOCTYPE, "re"))
```

### Português (para captar literatura regional)
```
TITLE-ABS-KEY(
 (enchent* OR inunda* OR alagament*)
 AND ("inteligência artificial" OR "aprendizado de máquina" OR "aprendizagem de máquina" OR "rede* neural*" OR LSTM OR "floresta aleatória" OR "gradiente reforçado")
 AND (costeir* OR litoral OR "zona costeira" OR maré OR "nível do mar")
)
AND (PUBYEAR > 1999 AND PUBYEAR < 2026)
AND (LIMIT-TO(DOCTYPE, "ar") OR LIMIT-TO(DOCTYPE, "re"))
```

---

## WEB OF SCIENCE (campos: TS = Tópico: título, resumo, palavras-chave)
Aplique filtros na aba Refine Results: Document Types: Article, Review; Timespan: 2000–2025.

### Global (costeira)
```
TS=(
 (flood* OR inundation* OR "flash flood*" OR "urban flooding")
 AND ("machine learning" OR "deep learning" OR "neural network*" OR LSTM OR "random forest" OR "gradient boosting" OR XGBoost)
 AND (coast* OR "coastal zone*" OR shoreline OR estuary OR "storm surge" OR tide OR "sea level")
)
```

### Brasil/SC reforço (opcional)
```
TS=(Brazil OR "Santa Catarina" OR Itajaí OR Florianópolis OR "Itajaí-Açu" OR "Vale do Itajaí")
```

### Português
```
TS=(
 (enchent* OR inunda* OR alagament*)
 AND ("inteligência artificial" OR "aprendizado de máquina" OR "aprendizagem de máquina" OR "rede* neural*" OR LSTM OR "floresta aleatória")
 AND (costeir* OR litoral OR "zona costeira" OR maré OR "nível do mar")
)
```

---

## OPENALEX (consulta por interface ou API; aqui, consulta de texto livre)
Pesquise por:
```
flood OR inundation "machine learning" OR "deep learning" LSTM "random forest" gradient boosting coastal OR "storm surge" tide
```
Depois filtre por: From 2000; Type: journal-article, review; Language: en, pt; Countries/Institutions se desejar.

Exportar em **BibTeX** ou **CSV** com campos completos.

---

## LENS.ORG (consulta no campo de busca + filtros)
Consulta:
```
(flood OR inundation OR "flash flood" OR "urban flooding")
AND ("machine learning" OR "deep learning" OR LSTM OR "neural network" OR "random forest" OR "gradient boosting")
AND (coastal OR "coastal zone" OR shoreline OR estuary OR "storm surge" OR tide)
```
Filtros: 2000–2025; Type: Scholarly Works; Article/Review.

---

## SCIELO (busca avançada, português e espanhol)
Consulta:
```
(enchentes OR inundações OR alagamentos) AND ("inteligência artificial" OR "aprendizado de máquina" OR "rede neural")
```
Refinar por área (Engenharia, Ciências Ambientais) e ano. Exportar RIS/BibTeX quando disponível.

---

## GOOGLE SCHOLAR (via Publish or Perish)
Consulta geral (Inglês):
```
(flood OR inundation) ("machine learning" OR "deep learning" OR LSTM OR "neural network" OR "random forest" OR "gradient boosting") (coastal OR "storm surge" OR tide OR shoreline)
```
Consulta PT-BR:
```
(enchentes OR inundações OR alagamentos) ("inteligência artificial" OR "aprendizado de máquina" OR "rede neural") (litoral OR "zona costeira" OR maré)
```
Limitar período 2000–2025. Exportar como BibTeX; depois você deduplica junto aos demais.

---

## Observações e variações úteis
- Acrescente termos de dados: `("remote sensing" OR "satellite" OR "SAR" OR "GIS")` para pegar integração geoespacial.
- Acrescente termos socioeconômicos: `("socioeconomic" OR "vulnerability" OR "social vulnerability" OR "IVS" OR "HDI" OR "population density")`.
- Experimentos: rode **com** e **sem** o bloco costeiro e, depois, filtre por assunto/região para comparar volumes.
- Evite vieses: não limite demais nos primeiros passes; refine com filtros após ver o volume/ruído.
