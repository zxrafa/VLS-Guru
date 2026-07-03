def main():
    filepath = "main.py"
    content = open(filepath, "r", encoding="utf-8").read()
    
    # 1. Update api_post_jogador definition
    post_start_idx = content.find('async def api_post_jogador(')
    if post_start_idx == -1:
        print("Could not find api_post_jogador")
        return
        
    post_end_idx = content.find('async def api_put_jogador(', post_start_idx)
    if post_end_idx == -1:
        print("Could not find api_put_jogador")
        return
        
    target_post = content[post_start_idx:post_end_idx]
    
    replacement_post = """async def api_post_jogador(request: web.Request) -> web.Response:
    data   = await request.post()
    name   = data.get("name", "Jogador")
    over   = int(data.get("over", 75))
    pos    = data.get("pos", "ST").upper()
    col_id = data.get("col_id", "")

    col_name, col_emoji, final_col_id = "Comum", "✨", "comum"
    if col_id:
        c_rec = await db_get(f"col_{col_id.lower().strip()}")
        if c_rec:
            col_name    = c_rec["data"]["nome"]
            col_emoji   = c_rec["data"]["emoji"]
            final_col_id = col_id.lower().strip()

    final_url = await _process_card_upload(data)

    player_id = f"player_{str(uuid.uuid4())[:8]}"
    player_data = {
        "id": player_id, "name": name, "over": over, "pos": pos,
        "card": final_url if final_url else "", "col_id": final_col_id, "col_nome": col_name, "col_emoji": col_emoji,
        "weak_foot": 3, "skill_moves": 3, "playstyles": [],
        "nationality": "Brasil", "club": "VLS FC", "xp": 0,
        # Outfield
        "pac": 75, "sho": 75, "pas": 75, "dri": 75, "def": 75, "phy": 75,
        # GK
        "div": 75, "han": 75, "kic": 75, "ref": 75, "spd": 75, "pos_stat": 75,
        # Compatibility
        "shoot": 75, "pass_stat": 75, "dribble": 75, "defense": 75, "physical": 75,
    }

    if not player_data["card"]:
        import asyncio
        from card_utils import generate_player_card_sync
        card_path = await asyncio.to_thread(generate_player_card_sync, player_data)
        if card_path:
            player_data["card"] = card_path

    await db_upsert(player_id, player_data)
    return web.json_response({"success": True})


"""
    
    # 2. Update api_put_jogador definition
    put_start_idx = content.find('async def api_put_jogador(')
    put_end_idx = content.find('async def api_delete_jogador(', put_start_idx)
    target_put = content[put_start_idx:put_end_idx]
    
    replacement_put = """async def api_put_jogador(request: web.Request) -> web.Response:
    player_id = request.match_info.get("id")
    data = await request.post()

    old_record = await db_get(player_id)
    if not old_record:
        return web.Response(text="Jogador não localizado.", status=404)

    old_data = old_record["data"]
    col_id   = data.get("col_id", "")
    col_name, col_emoji, final_col_id = old_data.get("col_nome", "Comum"), old_data.get("col_emoji", "✨"), old_data.get("col_id", "comum")

    if col_id:
        c_rec = await db_get(f"col_{col_id.lower().strip()}")
        if c_rec:
            col_name    = c_rec["data"]["nome"]
            col_emoji   = c_rec["data"]["emoji"]
            final_col_id = col_id.lower().strip()

    final_url = await _process_card_upload(data, fallback=old_data.get("card", ""))

    updated = old_data.copy()
    updated.update({
        "name": data.get("name", old_data["name"]),
        "over":  int(data.get("over", old_data["over"])),
        "pos":   data.get("pos", old_data["pos"]).upper(),
        "card":  final_url,
        "col_id": final_col_id, "col_nome": col_name, "col_emoji": col_emoji,
    })

    # Regerar card se mudou de coleção ou nome, e não tem upload manual
    if (old_data.get("col_id") != final_col_id or old_data.get("name") != updated["name"]) and not data.get("image"):
        import asyncio
        from card_utils import generate_player_card_sync
        card_path = await asyncio.to_thread(generate_player_card_sync, updated)
        if card_path:
            updated["card"] = card_path

    await db_upsert(player_id, updated)
    return web.json_response({"success": True})


"""

    content = content.replace(target_post, replacement_post)
    # Reload find coordinates because main file changed
    put_start_idx = content.find('async def api_put_jogador(')
    put_end_idx = content.find('async def api_delete_jogador(', put_start_idx)
    target_put = content[put_start_idx:put_end_idx]
    
    content = content.replace(target_put, replacement_put)
    
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
        
    print("main.py patched successfully!")

if __name__ == "__main__":
    main()
