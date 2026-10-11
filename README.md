# Google Maps Scraper

Scraper de estabelecimentos no Google Maps **sem usar a API oficial** (gratuito), construído com Selenium.

## Instalação

```bash
# Clone ou copie os arquivos para uma pasta
cd /caminho/para/a/pasta

# Crie um ambiente virtual (recomendado)
python3 -m venv .venv
source .venv/bin/activate

# Instale as dependências
pip install -r requirements.txt
```

## Uso

```bash
# Busca básica
python3 google_maps_scraper.py "restaurantes"

# Com localização
python3 google_maps_scraper.py "farmácias" --location "Curitiba, PR"

# Limitar resultados e prefixo de saída
python3 google_maps_scraper.py "hotéis" --location "Rio de Janeiro, RJ" --max-results 30 --output hoteis_rj

# Modo visível (sem headless) para debug
python3 google_maps_scraper.py "supermercados" --no-headless

# Mais rodadas de scroll (mais resultados)
python3 google_maps_scraper.py "cafés" --scroll-rounds 10
```

## Argumentos

| Argumento | Padrão | Descrição |
|---|---|---|
| `query` | _(obrigatório)_ | Termo de busca |
| `--location`, `-l` | _(vazio)_ | Localização geográfica |
| `--max-results`, `-n` | `20` | Número máximo de resultados |
| `--no-headless` | _(falso)_ | Abre navegador visível para debug |
| `--output`, `-o` | `resultados` | Prefixo dos arquivos de saída |
| `--scroll-rounds` | `5` | Rodadas de scroll para carregar mais itens |

## Saída

Dois arquivos são gerados:

- **`<output>.csv`** — planilha com todos os campos
- **`<output>.json`** — dados estruturados em JSON

Campos extraídos por estabelecimento:

| Campo | Descrição |
|---|---|
| `name` | Nome do estabelecimento |
| `address` | Endereço completo |
| `rating` | Nota (ex: `4.5`) |
| `reviews_count` | Número de avaliações |
| `phone` | Telefone |
| `website` | Site oficial |
| `category` | Categoria/tipo |
| `hours` | Horário de funcionamento |
| `maps_url` | URL do Google Maps |

## Notas

- O script usa **delays aleatórios** entre as ações para evitar bloqueio por bot.
- O modo **headless** (padrão) não abre janela do navegador.
- O **webdriver-manager** baixa o ChromeDriver correto automaticamente; é necessário ter o Google Chrome instalado.
- O Google Maps muda seus seletores CSS com frequência. Se o scraper parar de funcionar, pode ser necessário atualizar os seletores no código.
- Use com responsabilidade: respeite os [Termos de Serviço do Google](https://policies.google.com/terms).

## Dependências

- [Selenium](https://selenium-python.readthedocs.io/) >= 4.15
- [webdriver-manager](https://github.com/SergeyPirogov/webdriver_manager) >= 4.0
