# 10 · Interpretação agronômica

> **Leia como hipóteses.** Esta página liga os números do projeto ao que se sabe do manejo do café arábica. Os dados **não confirmam nem refutam** os mecanismos; eles apenas mostram o que é **compatível** com eles. Para decisão técnica, consulte um agrônomo e dados da propriedade.

## 1. Fenologia que justifica as janelas climáticas

| Fase (hemisfério sul) | Meses típicos | Sensibilidade | Feature do projeto |
|---|---|---|---|
| Indução e diferenciação floral | mar–jun | déficit hídrico leve estimula o processo | (não modelado) |
| Florada | set–nov | chuva após período seco sincroniza a florada; calor/seca abortam flores | `chuva_floracao`, `tmean_floracao` |
| Chumbinho e expansão | out–dez | água para expansão do fruto | `chuva_granacao` (parte) |
| Granação (enchimento) | dez–mar | calor e déficit hídrico reduzem peso e qualidade do grão | `chuva_granacao`, `tmax_granacao` |
| Maturação e colheita | abr–set | chuva na colheita prejudica a qualidade | — |
| Repouso e inverno | jun–ago | geada danifica ramos e gemas | `dias_frio_inv_prev` |

**Simplificação:** as épocas variam com região, altitude e cultivar. O limiar de **4 °C na mínima** é um *proxy* para risco de frio na **grade de ~55 km**; geadas locais (baixadas, "bolsões frios") não aparecem na reanálise e **ocorrem com temperaturas de grade bem acima de 4 °C**.

## 2. Bienalidade

O cafeeiro arábica tende a alternar safras altas e baixas: uma carga alta esgota reservas e reduz a formação de ramos produtivos para o ano seguinte.

O que os dados mostram:

- **Nível estadual** (notebooks 04 e 05): alternância forte. Autocorrelação lag 1 do rendimento estadual sem tendência ≈ **−0,66**; na produção CONAB (arábica SP) ≈ **−0,64**, com lag 2 ≈ **+0,70**; ≈ 91% dos anos invertem o sinal da variação.
- **Nível municipal:** a persistência é **positiva** (+0,23), porque anomalias herdam a **tendência** e as **estimativas repetidas** (38,5% dos pares com rendimento idêntico).
- **Implicação:** o que parece "tendência de queda" ou "alta" entre dois anos pode ser **ritmo bienal**. Compare sempre médias de vários anos.

**O que não se sabe aqui:** quanto da bienalidade é fisiológica e quanto vem de manejo (poda, esqueletamento, renovação) ou de geadas/secas pontuais.

## 3. Queda da área e aumento do rendimento

Nos dados da PAM (café total, SP): a **área colhida caiu de ≈ 908 mil ha (máx.) para ≈ 194 mil ha (2025)**; a produção caiu ≈ 74% desde o pico (1981); o rendimento (média de 5 anos) passou de ≈ 1 287 kg/ha (1974–78) para ≈ 1 618 kg/ha (2021–25).

Hipóteses **compatíveis** (não testadas): abandono das áreas menos produtivas, renovação de cafezais, melhoria de cultivares e manejo, deslocamento para regiões de altitude. **Os dados não separam esses efeitos.**

## 4. Regiões e altitude

- Maiores áreas: Ribeirão Preto (≈ 42% da área média 2021–25) e Campinas (≈ 27%).
- Maiores rendimentos médios: Assis (≈ 1 982 kg/ha, IC largo), Ribeirão Preto (≈ 1 725); menores: Presidente Prudente, Araçatuba, São José do Rio Preto (≈ 990–1 120).
- **Altitude × rendimento municipal:** ρ ≈ 0,48 (IC ≈ 0,40–0,57). Compatível com o fato de o arábica preferir clima mais ameno, **mas** altitude também correlaciona com solo, cultivar, tecnologia e tradição de cultivo. A altitude usada é a da **célula** (~55 km), não da lavoura.

## 5. Clima × produtividade

Nenhuma das seis features tem associação distinguível de zero (|ρ| ≤ 0,09; ICs incluem 0). Razões possíveis (não excludentes):

1. **Resolução:** 55 km não vê relevo nem microclima.
2. **Poucas safras independentes** (≈ 13).
3. **Ruído no alvo** (estimativas repetidas).
4. **Confusão** com bienalidade e manejo.
5. **Choques raros e fortes** (geada severa, seca) se diluem em médias.

**Não concluir** que clima não importa.

## 6. Preço e produção

Entre variações anuais, a correlação de postos é ≈ −0,06 (mesmo ano) e ≈ −0,17 (preço defasado), ambas com IC incluindo 0 (n ≈ 23–24). Um choque climático **generalizado** tende a elevar o preço e reduzir a oferta, mas o dado **não demonstra** isso aqui.

## 7. Leituras erradas comuns

| Leitura errada | Por quê |
|---|---|
| "Chuva na florada aumenta o rendimento em X%" | associação não é efeito; IC inclui 0 |
| "A região mais produtiva é Assis" | IC largo; sobrepõe Ribeirão Preto |
| "A produção está caindo todo ano" | série com bienalidade; use média móvel |
| "O modelo prevê a geada" | a grade de 55 km não vê geada local |
| "Plante acima de X metros" | associação de altitude de célula |

## 8. O que um produtor pode usar

- **Média de safras recentes** como referência (não o último ano).
- **Intervalos** (±5–25% regional) em vez de pontos.
- **Dados próprios por talhão** (idade, poda, adubação, estação local).
- Esta análise pública como **contexto regional**, não como recomendação agronômica.
