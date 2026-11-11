
# Checklist de exportação — campos e formatos

Marque cada item ao exportar os resultados das buscas.

## Scopus
- [ ] Formato: **CSV** (Complete), e opcional **RIS**/**BibTeX**
- [ ] Campos: Title, Authors, Affiliations, Abstract, Author Keywords, Index Keywords, Year, Source title (Journal), Volume/Issue/Pages, DOI, References, Country/Territory, Subject Area, Funding details
- [ ] Filtros aplicados anotados: Ano, Tipo de documento, Idioma
- [ ] Nome do arquivo exemplo: `scopus_export_YYYYMMDD.csv`

## Web of Science (Core Collection)
- [ ] Formato: **Plain Text** (para Bibliometrix) ou **CSV**
- [ ] Campos: Full Record and Cited References (título, autores, endereços, resumo, keywords, categorias, referências)
- [ ] Filtros anotados: Timespan, Document Types
- [ ] Nome: `wos_export_YYYYMMDD.txt`

## OpenAlex
- [ ] Formato: **BibTeX** ou **CSV**
- [ ] Campos: título, autores (com afiliação/país), ano, venue, abstract, keywords (quando houver), referências, DOI
- [ ] Nome: `openalex_export_YYYYMMDD.bib`

## Lens.org
- [ ] Formato: **CSV**
- [ ] Campos: título, autores, afiliações, resumo, keywords, ano, journal, referências (quando disponível), DOI
- [ ] Nome: `lens_export_YYYYMMDD.csv`

## SciELO
- [ ] Formato: **RIS** ou **BibTeX** (quando disponível)
- [ ] Campos: título, autores, resumo, periódico, ano, palavras-chave, DOI
- [ ] Nome: `scielo_export_YYYYMMDD.ris`

## Google Scholar (via Publish or Perish)
- [ ] Formato: **BibTeX** ou **RIS**
- [ ] Campos: título, autores, ano, periódico, citações (contagem), link/DOI
- [ ] Nome: `scholar_pop_export_YYYYMMDD.bib`

---

## Boas práticas
- [ ] Registrar **data da busca** e **string exata** utilizada (copiar e salvar)
- [ ] Manter **um arquivo por base** (não misturar)
- [ ] Evitar exportar mais do que 2–3 mil registros por arquivo (divida em lotes se necessário)
- [ ] Guardar uma planilha `log_buscas.xlsx` com: Base, String, Data/Hora, Filtros, Nº retornos, Arquivo gerado
