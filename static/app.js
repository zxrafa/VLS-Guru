// ==========================================
// CONFIGURAÇÕES E ESTADO GLOBAL DO APP
// ==========================================
const API_BASE = ""; // As rotas de API residem no mesmo servidor do bot
let currentUser = null;
let currentTab = "tab-overview";
let collectionsMap = {}; // ID -> Nome + Emoji
let allPlayers = [];
let allMembers = [];

// Funções Utilitárias para Emojis do Discord
function parseDiscordEmoji(text) {
    if (!text) return "";
    // Regex para capturar <:name:id> ou <a:name:id>
    const regex = /<a?:[a-zA-Z0-9_]+:([0-9]+)>/g;
    return text.replace(regex, (match, id) => {
        return `<img class="discord-emoji" src="https://cdn.discordapp.com/emojis/${id}.png" alt="emoji">`;
    });
}

function cleanDiscordEmojiText(text) {
    if (!text) return "";
    return text.replace(/<a?:([a-zA-Z0-9_]+):[0-9]+>/g, "$1");
}

// ==========================================
// INICIALIZAÇÃO E AUTENTICAÇÃO
// ==========================================
document.addEventListener("DOMContentLoaded", async () => {
    initTabNavigation();
    initFormHandlers();
    initModalControls();
    
    // Checa status de login
    await checkAuthStatus();
});

async function checkAuthStatus() {
    try {
        const res = await fetch("/api/auth/status");
        if (res.status === 200) {
            const data = await res.json();
            if (data.logged_in && data.is_admin) {
                currentUser = data.user;
                showAppScreen();
                loadInitialData();
            } else {
                showLoginScreen();
            }
        } else {
            showLoginScreen();
        }
    } catch (err) {
        console.error("Erro ao verificar autenticação:", err);
        showLoginScreen();
    }
}

function showLoginScreen() {
    document.getElementById("login-screen").style.display = "flex";
    document.getElementById("app-screen").style.display = "none";
}

function showAppScreen() {
    document.getElementById("login-screen").style.display = "none";
    document.getElementById("app-screen").style.display = "flex";
    
    // Atualiza info do usuário logado na sidebar
    document.getElementById("user-name").textContent = currentUser.username;
    if (currentUser.avatar) {
        document.getElementById("user-avatar").src = `https://cdn.discordapp.com/avatars/${currentUser.id}/${currentUser.avatar}.png`;
    } else {
        document.getElementById("user-avatar").src = "https://cdn.discordapp.com/embed/avatars/0.png";
    }
}

// ==========================================
// NAVEGAÇÃO DE ABAS
// ==========================================
function initTabNavigation() {
    const menuItems = document.querySelectorAll(".menu-item");
    menuItems.forEach(item => {
        item.addEventListener("click", () => {
            const tabId = item.getAttribute("data-tab");
            switchTab(tabId);
            
            // Atualiza classe ativa nos botões da sidebar
            menuItems.forEach(btn => btn.classList.remove("active"));
            item.classList.add("active");
        });
    });

    // Logout
    document.getElementById("btn-logout").addEventListener("click", async () => {
        await fetch("/api/auth/logout");
        showToast("Sessão encerrada com sucesso.", "info");
        showLoginScreen();
    });

    // Ações Rápidas
    document.getElementById("quick-add-player").addEventListener("click", () => {
        switchTab("tab-players");
        openPlayerModal();
    });
    document.getElementById("quick-create-col").addEventListener("click", () => {
        switchTab("tab-collections");
        openCollectionModal();
    });
}

function switchTab(tabId) {
    currentTab = tabId;
    
    // Esconde todos os conteúdos
    const contents = document.querySelectorAll(".tab-content");
    contents.forEach(content => content.classList.remove("active"));
    
    // Mostra a aba selecionada
    document.getElementById(tabId).classList.add("active");
    
    // Atualiza título da topbar
    const titles = {
        "tab-overview": "Visão Geral",
        "tab-players": "Gerenciar Jogadores",
        "tab-members": "Membros & Managers",
        "tab-collections": "Coleções Cadastradas"
    };
    document.getElementById("tab-title").textContent = titles[tabId] || "Dashboard";

    // Recarrega dados específicos
    if (tabId === "tab-players") loadPlayers();
    if (tabId === "tab-members") loadMembers();
    if (tabId === "tab-collections") loadCollections();
    if (tabId === "tab-overview") loadOverviewStats();
}

// ==========================================
// CARREGAMENTO DE DADOS (API)
// ==========================================
async function loadInitialData() {
    await loadCollections(); // Carrega coleções primeiro para mapear nomes nos cards
    loadOverviewStats();
}

async function loadOverviewStats() {
    try {
        const res = await fetch("/api/stats");
        if (res.ok) {
            const stats = await res.json();
            document.getElementById("stat-total-players").textContent = stats.total_players;
            document.getElementById("stat-total-users").textContent = stats.total_users;
            document.getElementById("stat-economy").textContent = `R$ ${stats.total_money.toLocaleString('pt-BR')}`;
        }
    } catch (err) {
        console.error("Erro ao carregar estatísticas gerais:", err);
    }
}

async function loadCollections() {
    try {
        const res = await fetch("/api/colecoes");
        if (res.ok) {
            const data = await res.json();
            collectionsMap = { "comum": { nome: "Comum", emoji: "✨" } };
            
            // Popula mapa de coleções
            data.forEach(c => {
                const id = c.id.replace("col_", "");
                collectionsMap[id] = { nome: c.data.nome, emoji: c.data.emoji };
            });

            // Popula selects de coleção nos filtros/modais
            populateCollectionSelects();
            renderCollectionsList(data);
        }
    } catch (err) {
        console.error("Erro ao carregar coleções:", err);
    }
}

function populateCollectionSelects() {
    const filterSelect = document.getElementById("filter-collection");
    const formSelect = document.getElementById("player-col");
    
    // Limpa selects mantendo a primeira opção padrão
    filterSelect.innerHTML = '<option value="">Todas Coleções</option>';
    formSelect.innerHTML = '<option value="comum">✨ Comum</option>';

    Object.keys(collectionsMap).forEach(key => {
        if (key === "comum") return;
        const col = collectionsMap[key];
        const emojiClean = col.emoji.includes("<") ? cleanDiscordEmojiText(col.emoji) : col.emoji;
        
        filterSelect.innerHTML += `<option value="${key}">${emojiClean} ${col.nome}</option>`;
        formSelect.innerHTML += `<option value="${key}">${emojiClean} ${col.nome}</option>`;
    });
}

async function loadPlayers() {
    try {
        const res = await fetch("/api/jogadores");
        if (res.ok) {
            allPlayers = await res.json();
            // Ordena jogadores por overall decrescente
            allPlayers.sort((a, b) => (b.data.over || 0) - (a.data.over || 0));
            renderPlayersList();
            
            // Popula também o select de dar jogador no modal de membros
            const givePlayerSelect = document.getElementById("select-give-player");
            givePlayerSelect.innerHTML = '<option value="">Escolha um jogador...</option>';
            allPlayers.forEach(p => {
                const col = collectionsMap[p.data.col_id || "comum"] || { emoji: "✨" };
                const emojiClean = col.emoji.includes("<") ? `[${cleanDiscordEmojiText(col.emoji)}]` : col.emoji;
                givePlayerSelect.innerHTML += `<option value="${p.id}">${emojiClean} ${p.data.name} (⭐${p.data.over} | ${p.data.pos})</option>`;
            });
        }
    } catch (err) {
        console.error("Erro ao carregar jogadores:", err);
    }
}

async function loadMembers() {
    try {
        const res = await fetch("/api/membros");
        if (res.ok) {
            allMembers = await res.json();
            renderMembersList();
        }
    } catch (err) {
        console.error("Erro ao carregar membros:", err);
    }
}

// ==========================================
// RENDERIZADORES DE TELA
// ==========================================
function renderPlayersList() {
    const listContainer = document.getElementById("players-list");
    listContainer.innerHTML = "";

    const query = document.getElementById("search-player").value.toLowerCase();
    const posFilter = document.getElementById("filter-position").value;
    const colFilter = document.getElementById("filter-collection").value;

    const filtered = allPlayers.filter(p => {
        const nameMatch = p.data.name.toLowerCase().includes(query);
        const posMatch = posFilter ? p.data.pos === posFilter : true;
        
        const cardColId = p.data.col_id || "comum";
        const colMatch = colFilter ? cardColId === colFilter : true;
        
        return nameMatch && posMatch && colMatch;
    });

    if (filtered.length === 0) {
        listContainer.innerHTML = `
            <div class="glass" style="grid-column: 1/-1; padding: 40px; text-align: center; color: var(--text-muted);">
                <i class="fa-solid fa-users-slash" style="font-size: 3rem; margin-bottom: 15px; display: block;"></i>
                Nenhum jogador encontrado com os filtros atuais.
            </div>
        `;
        return;
    }

    filtered.forEach(p => {
        const data = p.data;
        const col = collectionsMap[data.col_id || "comum"] || { nome: "Comum", emoji: "✨" };
        const cardImage = data.card || "https://i.imgur.com/83p5H1h.png"; // Placeholder elegante se n tiver
        
        const cardHtml = `
            <div class="player-card glass">
                <div class="card-top-info">
                    <span class="card-over">⭐ ${data.over}</span>
                    <span class="card-pos">${data.pos}</span>
                </div>
                <div class="card-image-container">
                    <img src="${cardImage}" alt="${data.name}" onerror="this.src='https://i.imgur.com/83p5H1h.png';">
                </div>
                <h4>${data.name}</h4>
                <div class="card-col-tag">
                    <span>${parseDiscordEmoji(col.emoji)} ${col.nome}</span>
                </div>
                <div class="card-actions">
                    <button class="btn btn-secondary" onclick="editPlayer('${p.id}')">
                        <i class="fa-solid fa-pen-to-square"></i>
                    </button>
                    <button class="btn btn-danger" onclick="deletePlayer('${p.id}', '${data.name}')">
                        <i class="fa-solid fa-trash"></i>
                    </button>
                </div>
            </div>
        `;
        listContainer.innerHTML += cardHtml;
    });
}

function renderMembersList() {
    const listContainer = document.getElementById("members-list");
    listContainer.innerHTML = "";

    const query = document.getElementById("search-member").value.toLowerCase();
    const filtered = allMembers.filter(m => {
        const usernameMatch = m.username.toLowerCase().includes(query);
        const clubMatch = m.club_name.toLowerCase().includes(query);
        return usernameMatch || clubMatch;
    });

    if (filtered.length === 0) {
        listContainer.innerHTML = `
            <tr>
                <td colspan="6" style="text-align: center; color: var(--text-muted); padding: 40px;">
                    Nenhum manager encontrado.
                </td>
            </tr>
        `;
        return;
    }

    filtered.forEach(m => {
        const avatarUrl = m.avatar 
            ? `https://cdn.discordapp.com/avatars/${m.id}/${m.avatar}.png`
            : "https://cdn.discordapp.com/embed/avatars/0.png";

        const rowHtml = `
            <tr>
                <td>
                    <div class="member-cell">
                        <img src="${avatarUrl}" alt="${m.username}">
                        <div>
                            <h4>${m.username}</h4>
                            <span>ID: ${m.id}</span>
                        </div>
                    </div>
                </td>
                <td class="club-name-cell">${m.club_name || "<em>Sem clube</em>"}</td>
                <td class="money-cell">R$ ${(m.money || 0).toLocaleString('pt-BR')}</td>
                <td class="premium-cell"><i class="fa-solid fa-coins" style="color: #a855f7; margin-right: 4px;"></i> ${(m.premium_coins || 0).toLocaleString('pt-BR')}</td>
                <td><i class="fa-solid fa-clone"></i> <strong>${(m.inventory || []).length}</strong> titulares/banco</td>
                <td>
                    <button class="btn btn-secondary" onclick="manageMember('${m.id}')">
                        <i class="fa-solid fa-sliders"></i> Gerenciar
                    </button>
                </td>
            </tr>
        `;
        listContainer.innerHTML += rowHtml;
    });
}

function renderCollectionsList(data) {
    const listContainer = document.getElementById("collections-list");
    listContainer.innerHTML = "";

    // Adiciona Coleção Comum Estática
    listContainer.innerHTML += `
        <div class="col-card glass">
            <div class="col-card-header">
                <div class="col-emoji-box">✨</div>
                <div class="col-title-box">
                    <h3>Comum</h3>
                    <span>Padrão</span>
                </div>
            </div>
            <div class="col-card-body">
                <p>Coleção padrão e base para todos os jogadores normais do bot.</p>
            </div>
            <div class="col-card-footer">
                <button class="btn btn-secondary" disabled>Coleção Sistema</button>
            </div>
        </div>
    `;

    data.forEach(c => {
        const id = c.id.replace("col_", "");
        const info = c.data;
        
        listContainer.innerHTML += `
            <div class="col-card glass">
                <div class="col-card-header">
                    <div class="col-emoji-box">${parseDiscordEmoji(info.emoji)}</div>
                    <div class="col-title-box">
                        <h3>${info.nome}</h3>
                        <span>Código: ${id}</span>
                    </div>
                </div>
                <div class="col-card-body">
                    <p>Coleção especial utilizada para cartas de tipo temático.</p>
                </div>
                <div class="col-card-footer">
                    <button class="btn btn-danger" onclick="deleteCollection('${c.id}', '${info.nome}')">
                        <i class="fa-solid fa-trash"></i> Deletar
                    </button>
                </div>
            </div>
        `;
    });
}

// ==========================================
// CONTROLES DE FILTROS E BUSCAS
// ==========================================
document.getElementById("search-player").addEventListener("input", renderPlayersList);
document.getElementById("filter-position").addEventListener("change", renderPlayersList);
document.getElementById("filter-collection").addEventListener("change", renderPlayersList);
document.getElementById("search-member").addEventListener("input", renderMembersList);

// ==========================================
// CONTROLE DE MODAIS (OPEN/CLOSE)
// ==========================================
function initModalControls() {
    // Fechar ao clicar no X ou fora
    const modals = document.querySelectorAll(".modal");
    modals.forEach(m => {
        m.addEventListener("click", (e) => {
            if (e.target === m) closeModal(m.id);
        });
    });

    document.getElementById("btn-close-player-modal").addEventListener("click", () => closeModal("modal-player"));
    document.getElementById("btn-close-member-modal").addEventListener("click", () => closeModal("modal-member"));
    document.getElementById("btn-close-col-modal").addEventListener("click", () => closeModal("modal-collection"));
    
    document.getElementById("btn-cancel-player").addEventListener("click", () => closeModal("modal-player"));
    document.getElementById("btn-cancel-col").addEventListener("click", () => closeModal("modal-collection"));
    
    document.getElementById("btn-add-player").addEventListener("click", () => openPlayerModal());
    document.getElementById("btn-add-collection").addEventListener("click", () => openCollectionModal());
}

function openModal(modalId) {
    document.getElementById(modalId).classList.add("active");
}

function closeModal(modalId) {
    document.getElementById(modalId).classList.remove("active");
}

// ==========================================
// FORMULÁRIO: JOGADORES (CRUD)
// ==========================================
function openPlayerModal(editId = null) {
    const form = document.getElementById("form-player");
    form.reset();
    document.getElementById("player-id").value = "";
    
    // Configura opções de imagem padrão
    document.getElementById("group-url").style.display = "block";
    document.getElementById("group-upload").style.display = "none";
    document.querySelector('input[name="img-source"][value="url"]').checked = true;

    if (editId) {
        document.getElementById("modal-player-title").textContent = "Editar Jogador";
        const p = allPlayers.find(x => x.id === editId);
        if (p) {
            document.getElementById("player-id").value = p.id;
            document.getElementById("player-name").value = p.data.name;
            document.getElementById("player-over").value = p.data.over;
            document.getElementById("player-pos").value = p.data.pos;
            document.getElementById("player-col").value = p.data.col_id || "comum";
            document.getElementById("player-img-url").value = p.data.card || "";
        }
    } else {
        document.getElementById("modal-player-title").textContent = "Adicionar Novo Jogador";
    }
    openModal("modal-player");
}

// Alternar entre URL e Upload do arquivo de imagem
const imgSourceRadios = document.querySelectorAll('input[name="img-source"]');
imgSourceRadios.forEach(radio => {
    radio.addEventListener("change", (e) => {
        if (e.target.value === "url") {
            document.getElementById("group-url").style.display = "block";
            document.getElementById("group-upload").style.display = "none";
        } else {
            document.getElementById("group-url").style.display = "none";
            document.getElementById("group-upload").style.display = "block";
        }
    });
});

window.editPlayer = function(id) {
    openPlayerModal(id);
};

window.deletePlayer = async function(id, name) {
    if (confirm(`Deseja realmente excluir permanentemente o jogador ${name}?`)) {
        try {
            const res = await fetch(`/api/jogadores/${id}`, { method: "DELETE" });
            if (res.ok) {
                showToast(`Jogador ${name} excluído.`, "success");
                loadPlayers();
            } else {
                showToast("Erro ao excluir jogador.", "error");
            }
        } catch (err) {
            showToast("Falha de conexão ao excluir.", "error");
        }
    }
};

// ==========================================
// FORMULÁRIO: COLEÇÕES (CRUD)
// ==========================================
function openCollectionModal() {
    document.getElementById("form-collection").reset();
    openModal("modal-collection");
}

window.deleteCollection = async function(id, name) {
    if (confirm(`Deseja realmente deletar a coleção "${name}"? Os jogadores vinculados a ela retornarão para a categoria "Comum".`)) {
        try {
            const cleanId = id.replace("col_", "");
            const res = await fetch(`/api/colecoes/${cleanId}`, { method: "DELETE" });
            if (res.ok) {
                showToast(`Coleção ${name} excluída.`, "success");
                loadCollections();
            } else {
                showToast("Erro ao excluir coleção.", "error");
            }
        } catch (err) {
            showToast("Erro de rede ao excluir coleção.", "error");
        }
    }
};

// ==========================================
// FORMULÁRIO: GERENCIAMENTO DE MEMBRO / MANAGER
// ==========================================
let currentMemberId = null;

window.manageMember = async function(id) {
    currentMemberId = id;
    const m = allMembers.find(x => x.id === id);
    if (!m) return;

    // Cabeçalho e Dados do Modal
    const avatarUrl = m.avatar 
        ? `https://cdn.discordapp.com/avatars/${m.id}/${m.avatar}.png`
        : "https://cdn.discordapp.com/embed/avatars/0.png";
        
    document.getElementById("member-modal-avatar").src = avatarUrl;
    document.getElementById("member-modal-name").textContent = m.username;
    document.getElementById("member-modal-club").textContent = m.club_name || "Sem clube criado";
    
    document.getElementById("member-modal-id").value = m.id;
    document.getElementById("member-money").value = m.money || 0;
    document.getElementById("member-premium").value = m.premium_coins || 0;

    // Reseta abas do modal
    const subtabs = document.querySelectorAll(".subtab-content");
    const tabBtns = document.querySelectorAll(".tab-btn");
    subtabs.forEach(t => t.classList.remove("active"));
    tabBtns.forEach(b => b.classList.remove("active"));
    
    document.getElementById("subtab-finance").classList.add("active");
    tabBtns[0].classList.add("active");

    // Renderiza elenco dele
    renderMemberInventory(m.inventory || []);

    openModal("modal-member");
};

// Configura botões de abas no modal de gerenciamento de membros
const subtabBtns = document.querySelectorAll(".tab-btn");
subtabBtns.forEach(btn => {
    btn.addEventListener("click", () => {
        const subtabId = btn.getAttribute("data-subtab");
        
        const subtabs = document.querySelectorAll(".subtab-content");
        subtabs.forEach(t => t.classList.remove("active"));
        document.getElementById(subtabId).classList.add("active");
        
        subtabBtns.forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
    });
});

function renderMemberInventory(inventory) {
    const list = document.getElementById("member-inventory-list");
    list.innerHTML = "";
    
    if (inventory.length === 0) {
        list.innerHTML = `<p style="grid-column:1/-1; text-align:center; padding: 20px; color: var(--text-muted); font-size:0.8rem;">Elenco vazio</p>`;
        return;
    }

    inventory.forEach((p, index) => {
        const col = collectionsMap[p.col_id || "comum"] || { emoji: "✨" };
        const img = p.card || "https://i.imgur.com/83p5H1h.png";
        
        list.innerHTML += `
            <div class="mini-player-item" onclick="removePlayerFromMember(${index})" title="Clique para remover este jogador do elenco do manager">
                <img src="${img}" alt="${p.name}" onerror="this.src='https://i.imgur.com/83p5H1h.png';">
                <span class="mini-over">⭐ ${p.over}</span>
                <span>${parseDiscordEmoji(col.emoji)} ${p.name}</span>
            </div>
        `;
    });
}

// Remover jogador do elenco de um membro
window.removePlayerFromMember = async function(playerIndex) {
    const m = allMembers.find(x => x.id === currentMemberId);
    if (!m) return;
    
    const p = m.inventory[playerIndex];
    if (confirm(`Deseja remover o jogador ${p.name} do elenco de ${m.username}?`)) {
        try {
            const res = await fetch(`/api/membros/${currentMemberId}/inventario/remover`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ index: playerIndex })
            });
            
            if (res.ok) {
                showToast(`${p.name} removido do clube com sucesso.`, "success");
                m.inventory.splice(playerIndex, 1); // Remove localmente no cache
                renderMemberInventory(m.inventory);
                loadMembers(); // Atualiza tela de fundo
            } else {
                showToast("Erro ao remover jogador.", "error");
            }
        } catch (err) {
            showToast("Falha de rede.", "error");
        }
    }
};

// Dar jogador para o membro
document.getElementById("btn-submit-give-player").addEventListener("click", async () => {
    const select = document.getElementById("select-give-player");
    const playerId = select.value;
    if (!playerId) return showToast("Selecione um jogador primeiro.", "info");

    const m = allMembers.find(x => x.id === currentMemberId);
    if (!m) return;

    const p = allPlayers.find(x => x.id === playerId);
    if (!p) return;

    try {
        const res = await fetch(`/api/membros/${currentMemberId}/inventario/adicionar`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ jogador: p.data })
        });
        
        if (res.ok) {
            showToast(`${p.data.name} adicionado ao elenco de ${m.username}!`, "success");
            m.inventory.push(p.data); // Atualiza cache
            renderMemberInventory(m.inventory);
            loadMembers();
        } else {
            showToast("Erro ao adicionar jogador.", "error");
        }
    } catch (err) {
        showToast("Falha na chamada de API.", "error");
    }
});

// ==========================================
// SUBMIT DE FORMULÁRIOS
// ==========================================
function initFormHandlers() {
    // Form Jogador (Criar / Editar)
    document.getElementById("form-player").addEventListener("submit", async (e) => {
        e.preventDefault();
        
        const id = document.getElementById("player-id").value;
        const name = document.getElementById("player-name").value;
        const over = document.getElementById("player-over").value;
        const pos = document.getElementById("player-pos").value;
        const col_id = document.getElementById("player-col").value;
        
        const imgSource = document.querySelector('input[name="img-source"]:checked').value;
        
        const formData = new FormData();
        formData.append("name", name);
        formData.append("over", over);
        formData.append("pos", pos);
        formData.append("col_id", col_id);

        if (imgSource === "url") {
            formData.append("card_url", document.getElementById("player-img-url").value);
        } else {
            const fileInput = document.getElementById("player-img-file");
            if (fileInput.files.length > 0) {
                formData.append("card_file", fileInput.files[0]);
            }
        }

        try {
            let res;
            if (id) {
                // Editar jogador existente
                res = await fetch(`/api/jogadores/${id}`, {
                    method: "PUT",
                    body: formData
                });
            } else {
                // Novo jogador
                res = await fetch("/api/jogadores", {
                    method: "POST",
                    body: formData
                });
            }

            if (res.ok) {
                showToast("Jogador salvo com sucesso!", "success");
                closeModal("modal-player");
                loadPlayers();
            } else {
                const text = await res.text();
                showToast(`Falha ao salvar: ${text}`, "error");
            }
        } catch (err) {
            showToast("Erro de rede ao salvar jogador.", "error");
        }
    });

    // Form Coleção (Criar)
    document.getElementById("form-collection").addEventListener("submit", async (e) => {
        e.preventDefault();
        
        const id = document.getElementById("col-id").value;
        const nome = document.getElementById("col-name").value;
        const emoji = document.getElementById("col-emoji").value;

        try {
            const res = await fetch("/api/colecoes", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ id, nome, emoji })
            });

            if (res.ok) {
                showToast(`Coleção "${nome}" criada com sucesso!`, "success");
                closeModal("modal-collection");
                loadCollections();
            } else {
                const text = await res.text();
                showToast(`Falha ao criar: ${text}`, "error");
            }
        } catch (err) {
            showToast("Erro de rede ao criar coleção.", "error");
        }
    });

    // Form Finanças do Membro
    document.getElementById("form-member-finance").addEventListener("submit", async (e) => {
        e.preventDefault();
        
        const id = document.getElementById("member-modal-id").value;
        const money = parseInt(document.getElementById("member-money").value);
        const premium_coins = parseInt(document.getElementById("member-premium").value);

        try {
            const res = await fetch(`/api/membros/${id}/finance`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ money, premium_coins })
            });

            if (res.ok) {
                showToast("Finanças salvas com sucesso!", "success");
                closeModal("modal-member");
                loadMembers();
            } else {
                showToast("Erro ao salvar finanças.", "error");
            }
        } catch (err) {
            showToast("Erro de conexão ao salvar finanças.", "error");
        }
    });
}

// ==========================================
// SISTEMA DE NOTIFICAÇÕES (TOAST)
// ==========================================
function showToast(message, type = "info") {
    const container = document.getElementById("toast-container");
    const toast = document.createElement("div");
    toast.className = `toast ${type}`;
    
    const icons = {
        success: "fa-circle-check",
        error: "fa-circle-exclamation",
        info: "fa-circle-info"
    };
    
    toast.innerHTML = `
        <i class="fa-solid ${icons[type] || 'fa-circle-info'}"></i>
        <span>${message}</span>
    `;
    
    container.appendChild(toast);
    
    // Auto-remove após 4 segundos
    setTimeout(() => {
        toast.style.animation = "slideIn 0.3s reverse forwards";
        toast.addEventListener("animationend", () => {
            toast.remove();
        });
    }, 4000);
}
