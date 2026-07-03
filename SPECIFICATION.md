# VLS Guru — Especificação Técnica do Reboot

> Bot novo, construído do zero em paralelo ao VLS Guru atual (que permanece ativo apenas na "S2", sem receber mais atualizações).
> Este documento é o guia de implementação para o Rafa (dev) a partir das decisões de design do Otávio.

## Diretriz de qualidade

O novo bot deve ter **todos os sistemas e comandos que o bot atual possui**, sem exceção — mas nenhum texto, embed, nome de variável ou mensagem deve ser copiado literalmente do código antigo. Tudo deve ser **reescrito com um padrão mais profissional**: copy mais limpo, embeds mais elegantes, nomenclatura consistente, sem gírias ou textos improvisados. A barra de qualidade visual e de produto deve subir em relação ao bot atual, mesmo nos comandos que mecanicamente fazem a mesma coisa.

---

## 1. Estrutura geral do projeto

- Bot novo, banco de dados separado do atual (Supabase em projeto/tabela própria).
- Reaproveitamento de **código-base** (estrutura de comandos, conexão com Supabase, servidor web) é aceitável; reaproveitamento de **cartas, jogadores e dados de usuários** não é.
- Moeda premium nova: `<:VLScoins:1517258837004914848>` substitui `💎` em todos os lugares.
- Escalação principal passa de 7 para **11 jogadores**.

---

## 2. Atributos da carta

Cada jogador, além dos campos já existentes (`name`, `over`, `pos`, `card`, `col_id`, `col_nome`, `col_emoji`), recebe:

```python
{
    "shoot": int,         # 0-99
    "pass_stat": int,     # 0-99
    "dribble": int,       # 0-99
    "defense": int,       # 0-99
    "physical": int,      # 0-99
    "weak_foot": int,     # 1-5 estrelas
    "skill_moves": int,   # 1-5 estrelas (fintas)
    "playstyles": list,   # lista de chaves, ex: ["trivela", "rapid"]
    "nationality": str,   # país do jogador (para química laranja/vermelha)
    "club": str,          # clube do jogador (para química verde/vermelha)
    "xp": int,            # acumulado de partidas jogadas pelo clube atual (afinidade)
}
```

`shoot`, `pass_stat`, `dribble`, `defense` e `physical` substituem o uso isolado de `over` nas fórmulas de chance da simulação — `over` continua existindo como nota geral exibida, mas os cálculos de chute, passe, drible e defesa passam a usar o atributo específico em vez do overall genérico.

### Limite de playstyles por carta — definido pela coleção

O número de playstyles de uma carta **não é fixo por raridade**: é um parâmetro configurável na criação da coleção, igual ao "preço adicional em %" que já existe.

- `criar_colecao` recebe um novo campo: `max_playstyles: int`.
- Ao usar `/add_jogador` ou `/edit_jogador` escolhendo aquela coleção, a interface deve impedir selecionar mais playstyles do que o limite definido na coleção.
- Coleção "Comum" tem `max_playstyles = 0` por padrão.

### Regra de elegibilidade por posição

- Goleiros (`GK`) só podem receber os playstyles exclusivos `arremesso_especial` e `encaixada`.
- Jogadores de linha nunca recebem os dois playstyles de goleiro, e podem receber qualquer um dos 9 genéricos restantes, respeitando o limite da coleção.

---

## 3. PlayStyles — efeitos e narração

| PlayStyle | Emoji | Restrição | Efeito mecânico |
|---|---|---|---|
| Técnica | `<:Tecnica:1517284475057344542>` | Linha | +3% chance de assistência; -10% chance de erro em domínio/passe |
| Trivela | `<:Trivela:1517284434670260234>` | Linha | +5% chance de acerto de passe |
| Rapid | `<:Rapid:1517284399765520472>` | Linha | +15% chance de vencer disputa de velocidade |
| Anjo | `<:Anjo:1517284298087071855>` | Linha | +25% chance de cabeceio defensivo bem-sucedido |
| Arremesso Especial | `<:ArremessoEspecial:1517284265233219584>` | **GK** | 15% chance do arremesso gerar assistência de gol |
| Encaixada | `<:Encaixada:1517284224821104711>` | **GK** | +25% chance de encaixar a bola (em vez de rebater) e sair jogando |
| Acrobata | `<:Acrobata:1517284020789182576>` | Linha | +5% voleio / +3% tesoura / +2% bicicleta como finalizações possíveis |
| SuperChute | `<:SuperChute:1517283994688028732>` | Linha | +10% chance de gol em chutes de fora da área |
| Malvadeza | `<:Malvadeza:1517283961762746430>` | Linha | +35% chance de drible bem-sucedido |
| Perde-Pressiona | `<:PerdePressiona:1517283755222503615>` | Linha | 60% chance de recuperar a bola imediatamente após perdê-la |
| Imã no Pé | `<:ImaNoPe:1517283715393257653>` | Linha | 95% chance de domínio perfeito |

```python
PLAYSTYLE_EMOJIS = {
    "tecnica": "<:Tecnica:1517284475057344542>",
    "trivela": "<:Trivela:1517284434670260234>",
    "rapid": "<:Rapid:1517284399765520472>",
    "anjo": "<:Anjo:1517284298087071855>",
    "arremesso_especial": "<:ArremessoEspecial:1517284265233219584>",
    "encaixada": "<:Encaixada:1517284224821104711>",
    "acrobata": "<:Acrobata:1517284020789182576>",
    "superchute": "<:SuperChute:1517283994688028732>",
    "malvadeza": "<:Malvadeza:1517283961762746430>",
    "perde_pressiona": "<:PerdePressiona:1517283755222503615>",
    "ima_no_pe": "<:ImaNoPe:1517283715393257653>",
}

VLS_COINS_EMOJI = "<:VLScoins:1517258837004914848>"
```

A narração deve checar, a cada lance simulado, se o jogador protagonista tem um playstyle relevante para aquele tipo de evento; se sim, sorteia a chance do playstyle e — em caso de sucesso — usa uma linha de narração própria (escrita do zero, em tom profissional e dinâmico, evitando repetir frases do bot atual). Caso o playstyle não ative, cai na narração genérica padrão.

---

## 4. Estrelas — perna ruim e finta

- `weak_foot` (1 a 5): jogadores ganham chance adicional de concluir bem jogadas com o pé não-dominante conforme mais estrelas.
  - Fórmula sugerida: `chance_pe_ruim = 0.40 + (weak_foot - 1) * 0.10` → varia de 40% a 80%.
- `skill_moves` (1 a 5): mais estrelas de finta aumentam a chance de sucesso em dribles.
  - Fórmula sugerida: `chance_finta = 0.30 + (skill_moves - 1) * 0.12` → varia de 30% a 78%.
  - Esse bônus **soma** (não multiplica) ao bônus do playstyle Malvadeza, se presente, para evitar valores fora de controle.

---

## 5. Tática de time (`/tatico`)

Escolhida **junto com a formação**, como uma camada independente — não substitui nada. Novo campo no perfil: `profile["tactic"]` (default `"padrao"`).

| Tática | Efeito |
|---|---|
| Padrão | Sem alterações |
| Gegenpress | +60% pressão/desarme após perda de bola; consumo de stamina/fadiga 30% mais rápido |
| Tiki-Taka | +15% precisão de passe; +10% organização de jogada; +25% de vulnerabilidade defensiva se um passe falhar |
| Catenaccio | +30% força defensiva; +15% sucesso em contra-ataque; -15% sucesso em jogadas de ataque |
| Futebol Total | +20% em finalizações, desarmes, recuperações e passes longos; -15% de precisão da linha defensiva |
| Park the Bus | +50% força defensiva; -35% de precisão nos ataques |

Implementação: multiplicadores globais aplicados nos thresholds de gol/defesa/passe da função de simulação de partida, de forma análoga ao sistema de pesos que já existe no código atual.

---

## 6. Escalação de 11 jogadores e `/escalar` em cascata

### Formações (8 no total, 11 jogadores cada)
4-3-3, 4-2-4, 4-2-3-1, 4-4-2, 3-5-2, 5-4-1, 3-4-3, 4-1-4-1.

A tabela de coordenadas (`get_formation_coords`) precisa ser reescrita do zero para 11 posições por formação, usando como referência os layouts visuais já produzidos pelo Otávio.

### Fluxo do `/escalar` (substitui a busca por nome digitado)

1. `/escalar` sem parâmetros abre uma `View` com um **Select de posição**, listando as posições da formação atual do usuário.
2. Ao escolher a posição, o callback filtra o inventário do usuário pelos jogadores elegíveis (incluindo improvisos de posição) e adiciona dinamicamente um **segundo Select de jogador**.
3. Ao escolher o jogador, ele é alocado naquela posição no `starting_xi`, substituindo quem estivesse lá.
4. A `View` permite repetir o fluxo para montar o time todo sem fechar o menu.

```python
POSITION_COMPATIBILITY = {
    "GK": ["GK"],
    "CB": ["CB", "LB", "RB"],
    "LB": ["LB", "CB"],
    "RB": ["RB", "CB"],
    "LWB": ["LWB", "LB", "LM"],
    "RWB": ["RWB", "RB", "RM"],
    "CDM": ["CDM", "CM"],
    "CM": ["CM", "CAM", "CDM", "LM", "RM"],
    "CAM": ["CAM", "CM"],
    "LM": ["LM", "CM", "LW"],
    "RM": ["RM", "CM", "RW"],
    "LW": ["LW", "LM"],
    "RW": ["RW", "RM"],
    "ST": ["ST", "CF"],
    "CF": ["CF", "ST"],
}

class PositionSelect(discord.ui.Select):
    def __init__(self, formation_positions):
        options = [discord.SelectOption(label=pos, value=pos) for pos in formation_positions]
        super().__init__(placeholder="Selecione a posição a escalar", options=options)

    async def callback(self, interaction: discord.Interaction):
        chosen_pos = self.values[0]
        profile = await get_user_profile(interaction.user)
        eligible_tags = POSITION_COMPATIBILITY.get(chosen_pos, [chosen_pos])
        eligible_players = [
            p for p in profile.get("inventory", [])
            if p.get("pos") in eligible_tags
        ][:25]

        view: EscalarView = self.view
        view.set_player_select(chosen_pos, eligible_players)
        await interaction.response.edit_message(view=view)


class PlayerSelect(discord.ui.Select):
    def __init__(self, target_pos, players):
        options = [
            discord.SelectOption(
                label=f"{p['name']} — ⭐{p['over']} ({p['pos']})",
                value=p["instance_id"],
            )
            for p in players
        ]
        super().__init__(placeholder=f"Selecione o jogador para {target_pos}", options=options)
        self.target_pos = target_pos

    async def callback(self, interaction: discord.Interaction):
        profile = await get_user_profile(interaction.user)
        chosen = next(
            (p for p in profile["inventory"] if p.get("instance_id") == self.values[0]), None
        )
        if not chosen:
            return await interaction.response.send_message("Jogador não encontrado no elenco.", ephemeral=True)

        chosen_copy = chosen.copy()
        chosen_copy["pos"] = self.target_pos

        xi = [p for p in profile.get("starting_xi", []) if p.get("pos") != self.target_pos]
        xi.append(chosen_copy)
        profile["starting_xi"] = xi
        await save_user_profile(interaction.user.id, profile)

        await interaction.response.send_message(
            f"{chosen['name']} escalado em {self.target_pos}.", ephemeral=True
        )


class EscalarView(discord.ui.View):
    def __init__(self, formation_positions):
        super().__init__(timeout=120)
        self.add_item(PositionSelect(formation_positions))

    def set_player_select(self, target_pos, players):
        self.children = [c for c in self.children if not isinstance(c, PlayerSelect)]
        self.add_item(PlayerSelect(target_pos, players))
```

> Esqueleto de referência — precisa de checagem de dono da interação e tratamento de erro/timeout, seguindo o padrão de segurança já usado no restante do bot.

---

## 7. Química de elenco

Calculada **por pares de vizinhança no campo**, e não pelo time inteiro.

- Para cada formação, define-se um mapa de adjacência entre as posições (ex: na 4-3-3, o lateral-direito é vizinho do zagueiro-direito e do meia-direita).
- Para cada par de jogadores vizinhos no `starting_xi`, verifica-se:
  - 🟠 **Laranja** — mesma nacionalidade
  - 🟢 **Verde** — mesmo clube
  - 🔴 **Vermelha** — mesmo clube **e** mesma nacionalidade (substitui laranja/verde daquele par específico; é o bônus mais alto, não soma com os outros dois no mesmo par)
- Bônus de pares diferentes **somam entre si** — um jogador com múltiplos vizinhos compatíveis acumula múltiplos bônus.
- O bônus afeta tanto os atributos (`shoot`, `pass_stat`, etc.) quanto o Overall final exibido na prancheta tática.

Valores sugeridos (ajustáveis):

| Nível | Bônus por par |
|---|---|
| Laranja | +1 em todos os atributos do jogador |
| Verde | +2 em todos os atributos do jogador |
| Vermelha | +3 em todos os atributos do jogador |

```python
def calculate_chemistry_bonus(starting_xi, formation_adjacency):
    bonuses = {p["instance_id"]: 0 for p in starting_xi}
    by_position = {p["pos"]: p for p in starting_xi}

    for pos_a, neighbors in formation_adjacency.items():
        player_a = by_position.get(pos_a)
        if not player_a:
            continue
        for pos_b in neighbors:
            player_b = by_position.get(pos_b)
            if not player_b or player_a["instance_id"] == player_b["instance_id"]:
                continue
            same_club = player_a.get("club") == player_b.get("club")
            same_country = player_a.get("nationality") == player_b.get("nationality")
            if same_club and same_country:
                bonuses[player_a["instance_id"]] += 3
            elif same_club:
                bonuses[player_a["instance_id"]] += 2
            elif same_country:
                bonuses[player_a["instance_id"]] += 1

    return bonuses
```

Esse bônus deve ser recalculado a cada simulação de partida e exibido na prancheta tática (`/time`) como um indicador visual (ex: ícone colorido ao lado do overall do jogador).

---

## 8. Afinidade (XP de clube)

- Cada jogador acumula `xp` por partida disputada no clube atual (PvP, treino e campeonato contam).
- A cada patamar de XP, o jogador ganha um pequeno bônus de chance de sucesso em ações ofensivas.
  - Sugestão de tabela: nível = `xp // 10` (1 nível a cada 10 partidas), bônus = `+0.5% por nível`, até um teto razoável (ex: 10 níveis, +5% máximo) para não distorcer o equilíbrio do jogo.
- O XP é zerado se o jogador for vendido ou trocado de clube (campo associado ao `instance_id`, não ao jogador genérico).
- Deve aparecer no `/show` (ver seção 11).

---

## 9. Upgrade de Olheiro

- Novo recurso por usuário: `profile["scout_level"]` (0 a 20).
- Cada nível aumenta o multiplicador de sorte aplicado aos pesos de raridade no `/recrutar`.
  - Sugestão: multiplicador = `1 + (scout_level * 0.03)` → nível 20 dá +60% de sorte.
- Upar o olheiro custa dinheiro crescente por nível (ex: custo = `nível atual * 50_000`), via novo comando `/upar_olheiro`.
- O nível do olheiro deve aparecer no `/perfil`.

---

## 10. Missões semanais e mensais

- Tabela de missões no Supabase, com tipo (`semanal`/`mensal`), critério (`vitorias`, `gols`, `partidas`, `recrutamentos`) e recompensa (dinheiro, moedas premium ou um jogador específico).
- Progresso do usuário rastreado em `profile["missions_progress"]`, resetado automaticamente conforme o ciclo (semanal toda segunda-feira, mensal todo dia 1).
- Comando `/missoes` exibe progresso atual e permite reivindicar recompensas completas.
- Comandos administrativos `/criar_missao` e `/remover_missao` para o time de design configurar sem precisar de deploy.

---

## 11. `/show` aprimorado

Expandir o comando de estatísticas do jogador para incluir:
- Cartões amarelos e vermelhos recebidos
- Gols esperados por partida (xG simplificado, calculado a partir do atributo `shoot` e da quantidade de finalizações registradas)
- Quantidade de vezes eleito MVP da partida
- Data de chegada ao clube (`acquired_at`, timestamp registrado no momento da contratação/recrutamento)
- Nível de afinidade atual (ver seção 8)

---

## 12. Sistema de Conquistas e Badges

Estrutura de dados sugerida:

```python
{
    "id": "artilheiro_iniciante",
    "category": "gols",
    "name": "Artilheiro Iniciante",
    "description": "Marque 50 gols com seus jogadores",
    "threshold": 50,
    "reward_type": "money",
    "reward_value": 10_000,
    "secret": False,
}
```

Categorias a implementar:
- **Gols** — marcos de gols totais do clube
- **Títulos** — marcos de campeonatos vencidos
- **Economia** — marcos de saldo acumulado
- **Coleção** — marcos de tamanho do elenco
- **Olheiro/Técnico** — marcos relacionados a contratações e ao sistema de olheiro
- **Secretas** — conquistas ocultas até serem desbloqueadas (ex: vencer uma partida revertendo desvantagem de 3 gols, tirar uma carta rara em um pacote, possuir uma carta de raridade máxima)

Conquistas e badges aparecem no `/perfil`, com uma badge em destaque escolhida pelo usuário (`profile["featured_badge"]`). Conquista suprema (todas as categorias completas) desbloqueia uma badge exclusiva e, opcionalmente, um cargo automático no servidor.

---

## 13. Itens explicitamente fora do código (conteúdo, não sistema)

- **Coleções de evento sazonal** (Páscoa, Natal etc.) não exigem lógica nova — usam o sistema de coleções e o painel administrativo já especificados. São criadas manualmente pela equipe via `/criar_colecao` + `/add_jogador`, com a única particularidade de serem removidas do mercado após o período do evento (`/deletar_colecao` quando o evento terminar).

---

## 14. Checklist de comandos finais (paridade com o bot atual + novidades)

Todos os comandos abaixo devem existir no bot novo, com nomes, descrições e textos de embed reescritos do zero:

**Economia e mercado:** caixa, loja, recrutar, mercado, contratar, vender, inventario, saldo, transferir, sobre, upar_olheiro, missoes

**Time e táticas:** time, escalar, tatico, perfil, renomear, estadio, xi, titular, banco, show

**Partidas:** desafio, x1_aposta, treino, ranking

**Campeonatos:** criar_campeonato, participar, rodar_jogo, campeonato, cancelar_campeonato

**Admin:** add_jogador, edit_jogador, del_jogador, add_dinheiro, remover_dinheiro, dar_jogador, tirar_jogador, criar_colecao, editar_colecao, deletar_colecao, remover_fundo, liberar_tudo, resetar_tudo, criar_missao, remover_missao

**Ajuda:** ajuda (reescrita com a lista de comandos atualizada, organizada por categoria, em tom mais profissional que o embed atual)
