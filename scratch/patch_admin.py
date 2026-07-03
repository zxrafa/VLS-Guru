import re

def main():
    filepath = "cogs/admin.py"
    content = open(filepath, "r", encoding="utf-8").read()
    
    # Locate where @app_commands.command(name="add_jogador" starts
    add_start_idx = content.find('@app_commands.command(name="add_jogador"')
    if add_start_idx == -1:
        print("Could not find @app_commands.command(name=\"add_jogador\")")
        return
        
    # Locate where the command after edit_jogador begins (del_jogador)
    del_start_idx = content.find('@app_commands.command(name="del_jogador"')
    if del_start_idx == -1:
        print("Could not find @app_commands.command(name=\"del_jogador\")")
        return
        
    # We want to replace the code from add_start_idx up to del_start_idx
    target_code = content[add_start_idx:del_start_idx]
    
    replacement_code = """@app_commands.command(name="add_jogador", description="[Admin] Adiciona uma carta modelo ao banco de dados global.")
    @app_commands.describe(
        id="ID único do jogador (ex: messi, CR7, neymar)",
        nome="Nome do jogador",
        overall="Nota Geral (OVR)",
        posicao="Posição natural (ex: ST, CB, GK)",
        colecao="ID da Coleção (ex: bronze, ouro)",
        attr_1="PAC (Velocidade) para Linha / DIV (Elasticidade) para GK (0-99)",
        attr_2="SHO (Chute) para Linha / HAN (Manejo) para GK (0-99)",
        attr_3="PAS (Passe) para Linha / KIC (Pontapé/Chute) para GK (0-99)",
        attr_4="DRI (Drible) para Linha / REF (Reflexo) para GK (0-99)",
        attr_5="DEF (Defesa) para Linha / SPD (Velocidade/Speed) para GK (0-99)",
        attr_6="PHY (Físico) para Linha / POS (Posicionamento) para GK (0-99)",
        weak_foot="Perna Ruim (1-5 estrelas)",
        skill_moves="Fintas (1-5 estrelas)",
        nacionalidade="Nacionalidade para Química",
        clube="Clube para Química",
        playstyles="Lista de PlayStyles (separados por vírgula. Ex: tecnica, trivela)",
        card="Caminho/URL da moldura customizada (opcional)"
    )
    async def add_jogador(
        self, interaction: discord.Interaction,
        id: str, nome: str, overall: int, posicao: str, colecao: str,
        attr_1: int, attr_2: int, attr_3: int, attr_4: int, attr_5: int, attr_6: int,
        weak_foot: int, skill_moves: int, nacionalidade: str, clube: str,
        playstyles: str = None, card: str = None
    ):
        if not self.is_admin(interaction):
            return await interaction.response.send_message("❌ Acesso negado.", ephemeral=True)

        await interaction.response.defer()

        # Validações de posições
        pos_upper = posicao.upper().strip()
        if pos_upper not in POSITIONS_ALL:
            return await interaction.followup.send(f"❌ Posição inválida. Escolha uma de: {', '.join(POSITIONS_ALL)}")

        # Validação de coleção
        col_doc = f"col_{colecao.lower()}"
        col_record = await db_get(col_doc)
        if not col_record:
            return await interaction.followup.send(f"❌ A coleção `{colecao}` não existe. Crie-a primeiro.")
        col_data = col_record["data"]

        # Tratamento de playstyles
        pstyle_list = []
        if playstyles:
            raw_styles = [p.strip().lower() for p in playstyles.split(",")]
            for p in raw_styles:
                if p not in PLAYSTYLE_EMOJIS:
                    return await interaction.followup.send(f"❌ PlayStyle inválido: `{p}`. Escolha entre: {', '.join(PLAYSTYLE_EMOJIS.keys())}")
                pstyle_list.append(p)

        # Valida limite de playstyles da coleção
        max_ps = col_data.get("max_playstyles", 0)
        if len(pstyle_list) > max_ps:
            return await interaction.followup.send(f"❌ Esta coleção suporta no máximo **{max_ps}** PlayStyles. Você indicou **{len(pstyle_list)}**.")

        # Regras de GK
        gk_styles = ["arremesso_especial", "encaixada"]
        for p in pstyle_list:
            if pos_upper == "GK" and p not in gk_styles:
                return await interaction.followup.send(f"❌ Goleiros (GK) só podem receber os PlayStyles exclusivos: {', '.join(gk_styles)}")
            if pos_upper != "GK" and p in gk_styles:
                return await interaction.followup.send(f"❌ Jogadores de linha não podem ter os PlayStyles exclusivos de GK ({', '.join(gk_styles)}).")

        doc_id = f"player_{id.lower().strip()}"
        player_exist = await db_get(doc_id)
        if player_exist:
            return await interaction.followup.send(f"❌ Um jogador com o ID `{id}` já existe no sistema.")

        is_gk = pos_upper == "GK"
        player_data = {
            "id": id.lower().strip(),
            "name": nome,
            "over": overall,
            "pos": pos_upper,
            "col_id": col_data["id"],
            "col_nome": col_data["nome"],
            "col_emoji": col_data["emoji"],
            "weak_foot": weak_foot,
            "skill_moves": skill_moves,
            "playstyles": pstyle_list,
            "nationality": nacionalidade,
            "club": clube,
            "card": card if card else "",
            "xp": 0
        }

        if is_gk:
            player_data.update({
                "div": attr_1,
                "han": attr_2,
                "kic": attr_3,
                "ref": attr_4,
                "spd": attr_5,
                "pos_stat": attr_6,
                # compatibility mapping
                "shoot": attr_3,
                "pass_stat": attr_2,
                "dribble": attr_4,
                "defense": attr_1,
                "physical": attr_6,
            })
        else:
            player_data.update({
                "pac": attr_1,
                "sho": attr_2,
                "pas": attr_3,
                "dri": attr_4,
                "def": attr_5,
                "phy": attr_6,
                # compatibility mapping
                "shoot": attr_2,
                "pass_stat": attr_3,
                "dribble": attr_4,
                "defense": attr_5,
                "physical": attr_6,
            })

        card_path = await asyncio.to_thread(generate_player_card_sync, player_data)
        if card_path:
            player_data["card"] = card_path

        await db_upsert(doc_id, player_data)

        embed = discord.Embed(
            title="🛡️ Novo Jogador Adicionado",
            description=f"O atleta **{nome}** foi cadastrado com sucesso no banco global.",
            color=discord.Color.gold()
        )
        embed.add_field(name="ID", value=f"`{id.lower().strip()}`", inline=True)
        embed.add_field(name="Posição/OVR", value=f"{pos_upper} (★ {overall})", inline=True)
        embed.add_field(name="Coleção", value=f"{col_data['emoji']} {col_data['nome']}", inline=True)
        embed.add_field(name="Perna Ruim / Fintas", value=f"⭐ {weak_foot} / ⭐ {skill_moves}", inline=True)
        embed.add_field(name="Clube & País", value=f"🏢 {clube} | 🏳️ {nacionalidade}", inline=True)
        ps_str = ", ".join([f"{PLAYSTYLE_EMOJIS[p]} {p.capitalize()}" for p in pstyle_list]) if pstyle_list else "Nenhum"
        embed.add_field(name="PlayStyles", value=ps_str, inline=False)
        embed.set_footer(text="VLS Guru • Gestão Esportiva")

        await interaction.followup.send(embed=embed)

    @app_commands.command(name="edit_jogador", description="[Admin] Edita dados de uma carta modelo.")
    @app_commands.describe(
        id="ID único do jogador cadastrado",
        nome="Novo nome (opcional)",
        overall="Novo overall (opcional)",
        posicao="Nova posição (opcional)",
        colecao="Nova coleção (opcional)",
        attr_1="PAC (Linha) ou DIV (GK) (opcional)",
        attr_2="SHO (Linha) ou HAN (GK) (opcional)",
        attr_3="PAS (Linha) ou KIC (GK) (opcional)",
        attr_4="DRI (Linha) ou REF (GK) (opcional)",
        attr_5="DEF (Linha) ou SPD (GK) (opcional)",
        attr_6="PHY (Linha) ou POS (GK) (opcional)",
        weak_foot="Perna Ruim (opcional)",
        skill_moves="Fintas (opcional)",
        nacionalidade="Nacionalidade (opcional)",
        clube="Clube (opcional)",
        playstyles="Playstyles separados por vírgula (opcional)",
        card="Nova moldura de carta (opcional)"
    )
    async def edit_jogador(
        self, interaction: discord.Interaction, id: str,
        nome: str = None, overall: int = None, posicao: str = None, colecao: str = None,
        attr_1: int = None, attr_2: int = None, attr_3: int = None, attr_4: int = None, attr_5: int = None, attr_6: int = None,
        weak_foot: int = None, skill_moves: int = None, nacionalidade: str = None, clube: str = None,
        playstyles: str = None, card: str = None
    ):
        if not self.is_admin(interaction):
            return await interaction.response.send_message("❌ Acesso negado.", ephemeral=True)

        await interaction.response.defer()

        doc_id = f"player_{id.lower().strip()}"
        record = await db_get(doc_id)
        if not record:
            return await interaction.followup.send("❌ Jogador não encontrado no banco.")

        p_data = record["data"]

        # Se mudou de posição ou coleção, precisamos revalidar
        new_pos = posicao.upper().strip() if posicao else p_data["pos"]
        if new_pos not in POSITIONS_ALL:
            return await interaction.followup.send("❌ Posição inválida.")

        new_col_id = colecao.lower().strip() if colecao else p_data["col_id"]
        col_doc = f"col_{new_col_id}"
        col_record = await db_get(col_doc)
        if not col_record:
            return await interaction.followup.send("❌ Coleção associada não existe.")
        col_data = col_record["data"]

        # Novas variáveis
        if nome: p_data["name"] = nome
        if overall is not None: p_data["over"] = overall
        p_data["pos"] = new_pos
        p_data["col_id"] = col_data["id"]
        p_data["col_nome"] = col_data["nome"]
        p_data["col_emoji"] = col_data["emoji"]
        if weak_foot is not None: p_data["weak_foot"] = weak_foot
        if skill_moves is not None: p_data["skill_moves"] = skill_moves
        if nacionalidade: p_data["nationality"] = nacionalidade
        if clube: p_data["club"] = clube
        if card is not None: p_data["card"] = card

        is_gk = new_pos == "GK"

        # Atualiza atributos baseados na posição
        if is_gk:
            if attr_1 is not None: p_data["div"] = attr_1
            if attr_2 is not None: p_data["han"] = attr_2
            if attr_3 is not None: p_data["kic"] = attr_3
            if attr_4 is not None: p_data["ref"] = attr_4
            if attr_5 is not None: p_data["spd"] = attr_5
            if attr_6 is not None: p_data["pos_stat"] = attr_6

            # Garante mapeamento de compatibilidade
            p_data["shoot"] = p_data.get("kic", 75)
            p_data["pass_stat"] = p_data.get("han", 75)
            p_data["dribble"] = p_data.get("ref", 75)
            p_data["defense"] = p_data.get("div", 75)
            p_data["physical"] = p_data.get("pos_stat", 75)
        else:
            if attr_1 is not None: p_data["pac"] = attr_1
            if attr_2 is not None: p_data["sho"] = attr_2
            if attr_3 is not None: p_data["pas"] = attr_3
            if attr_4 is not None: p_data["dri"] = attr_4
            if attr_5 is not None: p_data["def"] = attr_5
            if attr_6 is not None: p_data["phy"] = attr_6

            # Garante mapeamento de compatibilidade
            p_data["shoot"] = p_data.get("sho", 75)
            p_data["pass_stat"] = p_data.get("pas", 75)
            p_data["dribble"] = p_data.get("dri", 75)
            p_data["defense"] = p_data.get("def", 75)
            p_data["physical"] = p_data.get("phy", 75)

        # PlayStyles
        if playstyles is not None:
            pstyle_list = []
            if playstyles.strip():
                raw_styles = [p.strip().lower() for p in playstyles.split(",")]
                for p in raw_styles:
                    if p not in PLAYSTYLE_EMOJIS:
                        return await interaction.followup.send(f"❌ PlayStyle inválido: `{p}`.")
                    pstyle_list.append(p)
            p_data["playstyles"] = pstyle_list

        # Validar limites
        max_ps = col_data.get("max_playstyles", 0)
        if len(p_data["playstyles"]) > max_ps:
            return await interaction.followup.send(f"❌ Coleção `{col_data['nome']}` suporta máximo de **{max_ps}** Playstyles. Esta carta possui **{len(p_data['playstyles'])}**.")

        gk_styles = ["arremesso_especial", "encaixada"]
        for p in p_data["playstyles"]:
            if new_pos == "GK" and p not in gk_styles:
                return await interaction.followup.send(f"❌ Goleiro só pode ter os playstyles: {gk_styles}")
            if new_pos != "GK" and p in gk_styles:
                return await interaction.followup.send(f"❌ Linha não pode ter playstyles de GK.")

        # Gerar card em thread separado
        card_path = await asyncio.to_thread(generate_player_card_sync, p_data)
        if card_path:
            p_data["card"] = card_path

        await db_upsert(doc_id, p_data)
        await interaction.followup.send(f"✅ Jogador **{p_data['name']}** atualizado com sucesso.")

    """
    
    new_content = content.replace(target_code, replacement_code)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(new_content)
    print("cogs/admin.py patched successfully!")

if __name__ == "__main__":
    main()
