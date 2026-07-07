// ==========================================
// CONFIGURAÇÕES E ESTADO GLOBAL DO APP
// ==========================================
let currentUser = null;
let currentTab = "tab-overview";
let allChampionships = [];
let allMatches = [];
let allLeaguePlayers = [];
let allNews = [];

// ==========================================
// INICIALIZAÇÃO E AUTENTICAÇÃO
// ==========================================
document.addEventListener("DOMContentLoaded", async () => {
    initTabNavigation();
    initFormHandlers();
    initModalControls();
    
    // Configura botão de submissão do PIN
    const btnSubmitPin = document.getElementById("btn-submit-pin");
    const inputPin = document.getElementById("admin-pin-input");
    const errPanel = document.getElementById("login-error-msg");

    const handlePinSubmit = () => {
        const pin = inputPin.value.trim();
        if (pin === "8888") {
            localStorage.setItem("admin_pin", "8888");
            errPanel.style.display = "none";
            showAppScreen();
            loadInitialData();
            showToast("Painel desbloqueado com sucesso!", "success");
        } else {
            errPanel.style.display = "block";
            inputPin.value = "";
        }
    };

    if (btnSubmitPin) {
        btnSubmitPin.addEventListener("click", handlePinSubmit);
    }
    if (inputPin) {
        inputPin.addEventListener("keypress", (e) => {
            if (e.key === "Enter") {
                handlePinSubmit();
            }
        });
    }

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
                
                // Se o usuário está logado via Discord, verifica o PIN local
                const savedPin = localStorage.getItem("admin_pin");
                if (savedPin === "8888") {
                    showAppScreen();
                    loadInitialData();
                } else {
                    // Logado no Discord, mas precisa digitar o PIN
                    showPinScreen(currentUser.global_name || currentUser.username);
                }
            } else {
                showDiscordLoginScreen();
            }
        } else {
            showDiscordLoginScreen();
        }
    } catch (err) {
        console.error("Erro ao verificar autenticação:", err);
        showDiscordLoginScreen();
    }
}

function showDiscordLoginScreen() {
    document.getElementById("login-screen").style.display = "flex";
    document.getElementById("login-step-discord").style.display = "flex";
    document.getElementById("login-step-pin").style.display = "none";
    document.getElementById("app-screen").style.display = "none";
}

function showPinScreen(adminName) {
    document.getElementById("login-screen").style.display = "flex";
    document.getElementById("login-step-discord").style.display = "none";
    document.getElementById("login-step-pin").style.display = "flex";
    document.getElementById("app-screen").style.display = "none";
    
    const welcomeMsg = document.getElementById("pin-welcome-msg");
    if (welcomeMsg) {
        welcomeMsg.innerHTML = `Olá, <strong>${adminName}</strong>! Insira o PIN de segurança para abrir o painel.`;
    }
}

function showAppScreen() {
    document.getElementById("login-screen").style.display = "none";
    document.getElementById("app-screen").style.display = "flex";
    
    // Mostra avatar e nome do admin
    if (currentUser) {
        document.getElementById("user-avatar").src = currentUser.avatar_url || "";
        document.getElementById("user-name").textContent = currentUser.global_name || currentUser.username;
    }
}

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
        localStorage.removeItem("admin_pin");
        await fetch("/api/auth/logout");
        showToast("Sessão encerrada com sucesso.", "info");
        showDiscordLoginScreen();
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
        "tab-championships": "Gerenciar Campeonatos",
        "tab-matches": "Confrontos & Resultados",
        "tab-league-players": "Artilharia & Notas",
        "tab-news": "Notícias da Liga"
    };
    document.getElementById("tab-title").textContent = titles[tabId] || "Dashboard";

    // Recarrega dados específicos
    if (tabId === "tab-championships") loadChampionships();
    if (tabId === "tab-matches") {
        loadChampionships().then(() => loadMatches());
    }
    if (tabId === "tab-league-players") {
        loadChampionships().then(() => loadLeaguePlayers());
    }
    if (tabId === "tab-news") loadNews();
    if (tabId === "tab-overview") loadOverviewStats();
}

async function loadInitialData() {
    await loadChampionships();
    loadOverviewStats();
}

async function loadOverviewStats() {
    try {
        const res = await fetch("/api/stats");
        if (res.ok) {
            const stats = await res.json();
            // Estatísticas rápidas para o painel da liga
            document.getElementById("stat-total-players").textContent = allChampionships.length;
            document.querySelector(".stat-card:nth-child(1) .stat-label").textContent = "Campeonatos";
            
            // Reutiliza os outros cards de forma inteligente
            const newsRes = await fetch("/api/public/noticias");
            const newsData = await newsRes.json();
            document.getElementById("stat-total-users").textContent = newsData.length;
            document.querySelector(".stat-card:nth-child(2) .stat-label").textContent = "Notícias Publicadas";

            const matchesRes = await fetch("/api/public/partidas");
            const matchesData = await matchesRes.json();
            document.getElementById("stat-economy").textContent = matchesData.length;
            document.querySelector(".stat-card:nth-child(3) .stat-label").textContent = "Jogos Cadastrados";
            document.querySelector(".stat-card:nth-child(3) .stat-icon").className = "stat-icon bg-gold";
            document.querySelector(".stat-card:nth-child(3) .stat-icon i").className = "fa-solid fa-calendar-days";
        }
    } catch (err) {
        console.error("Erro ao carregar estatísticas gerais:", err);
    }
}

// ==========================================
// MODAIS CONTROLE
// ==========================================
function initModalControls() {
    const modals = document.querySelectorAll(".modal");
    modals.forEach(m => {
        m.addEventListener("click", (e) => {
            if (e.target === m) closeModal(m.id);
        });
    });

    document.getElementById("btn-close-championship-modal").addEventListener("click", () => closeModal("modal-championship"));
    document.getElementById("btn-close-match-modal").addEventListener("click", () => closeModal("modal-match"));
    document.getElementById("btn-close-news-modal").addEventListener("click", () => closeModal("modal-news"));
    document.getElementById("btn-close-league-player-modal").addEventListener("click", () => closeModal("modal-league-player"));
    document.getElementById("btn-close-teams-modal").addEventListener("click", () => closeModal("modal-teams"));
    
    document.getElementById("btn-cancel-championship").addEventListener("click", () => closeModal("modal-championship"));
    document.getElementById("btn-cancel-match").addEventListener("click", () => closeModal("modal-match"));
    document.getElementById("btn-cancel-news").addEventListener("click", () => closeModal("modal-news"));
    document.getElementById("btn-cancel-league-player").addEventListener("click", () => closeModal("modal-league-player"));
    
    document.getElementById("btn-add-championship").addEventListener("click", () => openChampionshipModal());
    document.getElementById("btn-add-match").addEventListener("click", () => openMatchModal());
    document.getElementById("btn-add-news").addEventListener("click", () => openNewsModal());
    document.getElementById("btn-add-league-player").addEventListener("click", () => openLeaguePlayerModal());

    document.getElementById("filter-match-championship").addEventListener("change", () => loadMatches());
    document.getElementById("filter-league-player-championship").addEventListener("change", () => loadLeaguePlayers());

    // Escuta a mudança de campeonato na criação do jogo para preencher os times
    document.getElementById("match-championship").addEventListener("change", (e) => {
        const campId = e.target.value;
        updateMatchTeamsSelects(campId);
    });
}

function openModal(modalId) {
    document.getElementById(modalId).classList.add("active");
}

function closeModal(modalId) {
    document.getElementById(modalId).classList.remove("active");
}

// ==========================================
// FORM HANDLERS
// ==========================================
function initFormHandlers() {
    // Form Campeonato
    document.getElementById("form-championship").addEventListener("submit", async (e) => {
        e.preventDefault();
        const id = document.getElementById("championship-id").value;
        const nome = document.getElementById("championship-name").value;
        const logoUrl = document.getElementById("championship-logo-url").value;
        const logoFile = document.getElementById("championship-logo-file").files[0];
        const ativo = document.getElementById("championship-active").checked;

        const formData = new FormData();
        if (id) formData.append("id", id);
        formData.append("nome", nome);
        formData.append("logo_url", logoUrl);
        if (logoFile) formData.append("logo_file", logoFile);
        formData.append("ativo", ativo ? "true" : "false");

        try {
            const res = await fetch("/api/campeonatos", { method: "POST", body: formData });
            if (res.ok) {
                showToast("Campeonato salvo com sucesso!", "success");
                closeModal("modal-championship");
                loadChampionships();
            } else {
                showToast(await res.text(), "error");
            }
        } catch (err) {
            showToast("Erro ao salvar campeonato.", "error");
        }
    });

    // Form Jogo
    document.getElementById("form-match").addEventListener("submit", async (e) => {
        e.preventDefault();
        const id = document.getElementById("match-id").value;
        const campeonato_id = document.getElementById("match-championship").value;
        const rodada = document.getElementById("match-round").value;
        const time_casa = document.getElementById("match-home").value;
        const time_fora = document.getElementById("match-away").value;
        const gols_casa = document.getElementById("match-gols-home").value;
        const gols_fora = document.getElementById("match-gols-away").value;
        const video_url = document.getElementById("match-video").value;
        const data_jogo = document.getElementById("match-date").value;
        const encerrada = document.getElementById("match-ended").checked;

        const payload = {
            id, campeonato_id, rodada, time_casa, time_fora,
            gols_casa, gols_fora, video_url, data_jogo, encerrada
        };

        try {
            const res = await fetch("/api/partidas", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });
            if (res.ok) {
                showToast("Partida salva com sucesso!", "success");
                closeModal("modal-match");
                loadMatches();
            } else {
                showToast(await res.text(), "error");
            }
        } catch (err) {
            showToast("Erro ao salvar partida.", "error");
        }
    });

    // Form Jogador da Liga (Estatísticas)
    document.getElementById("form-league-player").addEventListener("submit", async (e) => {
        e.preventDefault();
        const id = document.getElementById("league-player-id").value;
        const campeonato_id = document.getElementById("league-player-championship").value;
        const nome = document.getElementById("league-player-name").value;
        const time = document.getElementById("league-player-team").value;
        const jogos = document.getElementById("league-player-matches").value;
        const gols = document.getElementById("league-player-goals").value;
        const assistencias = document.getElementById("league-player-assists").value;
        const nota_media = document.getElementById("league-player-rating").value;

        const payload = {
            id, campeonato_id, nome, time,
            jogos: jogos ? parseInt(jogos) : 0,
            gols: gols ? parseInt(gols) : 0,
            assistencias: assistencias ? parseInt(assistencias) : 0,
            nota_media: nota_media ? parseFloat(nota_media) : 0.0
        };

        try {
            const res = await fetch("/api/jogadores_liga", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });
            if (res.ok) {
                showToast("Estatísticas do jogador salvas!", "success");
                closeModal("modal-league-player");
                loadLeaguePlayers();
            } else {
                showToast(await res.text(), "error");
            }
        } catch (err) {
            showToast("Erro ao salvar jogador.", "error");
        }
    });

    // Form Notícia
    document.getElementById("form-news").addEventListener("submit", async (e) => {
        e.preventDefault();
        const id = document.getElementById("news-id").value;
        const titulo = document.getElementById("news-title").value;
        const subtitulo = document.getElementById("news-subtitle").value;
        const imagemUrl = document.getElementById("news-image-url").value;
        const imagemFile = document.getElementById("news-image-file").files[0];
        const conteudo = document.getElementById("news-content").value;

        const formData = new FormData();
        if (id) formData.append("id", id);
        formData.append("titulo", titulo);
        formData.append("subtitulo", subtitulo);
        formData.append("imagem_url", imagemUrl);
        if (imagemFile) formData.append("imagem_file", imagemFile);
        formData.append("conteudo", conteudo);

        try {
            const res = await fetch("/api/noticias", { method: "POST", body: formData });
            if (res.ok) {
                showToast("Notícia publicada com sucesso!", "success");
                closeModal("modal-news");
                loadNews();
            } else {
                showToast(await res.text(), "error");
            }
        } catch (err) {
            showToast("Erro ao publicar notícia.", "error");
        }
    });

    // Form Adicionar Time no Campeonato
    document.getElementById("form-add-time").addEventListener("submit", async (e) => {
        e.preventDefault();
        const campId = document.getElementById("teams-camp-id").value;
        const nome = document.getElementById("new-team-name").value.trim();
        if (!nome || !campId) return;

        const formData = new FormData();
        formData.append("nome", nome);

        try {
            const res = await fetch(`/api/campeonatos/${campId}/times`, { method: "POST", body: formData });
            if (res.ok) {
                showToast("Time adicionado com sucesso!", "success");
                document.getElementById("new-team-name").value = "";
                loadChampionshipTeams(campId);
            } else {
                showToast(await res.text(), "error");
            }
        } catch (err) {
            showToast("Erro ao adicionar time.", "error");
        }
    });
}

// ==========================================
// CAMPEONATOS CRUD
// ==========================================
async function loadChampionships() {
    try {
        const res = await fetch("/api/public/campeonatos");
        if (res.ok) {
            allChampionships = await res.json();
            updateChampionshipDropdowns();
            renderChampionshipsList();
        }
    } catch (err) {
        console.error("Erro ao carregar campeonatos:", err);
    }
}

function updateChampionshipDropdowns() {
    const filterMatch = document.getElementById("filter-match-championship");
    const filterPlayer = document.getElementById("filter-league-player-championship");
    const modalMatch = document.getElementById("match-championship");
    const modalPlayer = document.getElementById("league-player-championship");
    
    const dropdowns = [
        { el: filterMatch, def: "Filtrar por Campeonato (Todos)" },
        { el: filterPlayer, def: "Filtrar por Campeonato (Todos)" },
        { el: modalMatch, def: "Selecione um campeonato..." },
        { el: modalPlayer, def: "Selecione um campeonato..." }
    ];

    dropdowns.forEach(d => {
        if (!d.el) return;
        const oldVal = d.el.value;
        d.el.innerHTML = `<option value="">${d.def}</option>`;
        allChampionships.forEach(c => {
            d.el.innerHTML += `<option value="${c.id}">${c.nome}</option>`;
        });
        d.el.value = oldVal;
    });
}

function renderChampionshipsList() {
    const listContainer = document.getElementById("championships-list");
    if (!listContainer) return;

    if (allChampionships.length === 0) {
        listContainer.innerHTML = '<div class="no-data-card glass">Nenhum campeonato cadastrado ainda.</div>';
        return;
    }

    listContainer.innerHTML = allChampionships.map(c => {
        const logo = c.logo_url || "https://i.ibb.co/C5B7BBjS/image.png";
        return `
            <div class="col-card glass" style="display: flex; flex-direction: column; gap: 0.85rem; padding: 1rem; border-radius: 12px; margin-bottom: 0px;">
                <div class="col-card-header" style="display: flex; align-items: center; justify-content: space-between; border-bottom: none; padding-bottom: 0; width: 100%;">
                    <div style="display: flex; align-items: center; gap: 0.75rem;">
                        <img src="${logo}" alt="${c.nome}" style="width: 44px; height: 44px; border-radius: 50%; object-fit: cover; background: rgba(255,255,255,0.05);" onerror="this.src='https://i.ibb.co/C5B7BBjS/image.png'">
                        <div>
                            <h4 style="font-weight:600; font-size:1.05rem; color: #fff; margin: 0;">${c.nome}</h4>
                            <span class="badge ${c.ativo ? 'badge-success' : 'badge-danger'}" style="font-size:0.65rem; padding: 0.15rem 0.5rem; border-radius: 20px; display: inline-block; margin-top: 0.25rem;">
                                ${c.ativo ? 'Ativo' : 'Inativo'}
                            </span>
                        </div>
                    </div>
                    <div class="col-card-actions" style="display: flex; gap: 0.35rem;">
                        <button class="btn-icon btn-edit-col" onclick="editChampionship('${c.id}')" title="Editar"><i class="fa-solid fa-pen-to-square"></i></button>
                        <button class="btn-icon btn-delete-col" onclick="deleteChampionship('${c.id}', '${c.nome}')" title="Excluir"><i class="fa-solid fa-trash"></i></button>
                    </div>
                </div>
                <div style="border-top: 1px solid rgba(255,255,255,0.08); padding-top: 0.75rem; width: 100%;">
                    <button class="btn btn-primary" onclick="openChampionshipTeamsModal('${c.id}', '${c.nome}')" style="background: rgba(0, 255, 255, 0.1); border: 1px solid rgba(0, 255, 255, 0.25); color: var(--color-cyan); font-weight: 700; width: 100%; justify-content: center; font-size: 0.75rem; padding: 0.45rem 1rem; border-radius: 8px; display: flex; align-items: center; gap: 0.5rem; cursor: pointer; transition: all 0.2s ease;">
                        <i class="fa-solid fa-shield-halved" style="font-size: 0.85rem;"></i> Gerenciar Times
                    </button>
                </div>
            </div>
        `;
    }).join("");
}

function openChampionshipModal(editId = null) {
    const form = document.getElementById("form-championship");
    form.reset();
    document.getElementById("championship-id").value = "";
    document.getElementById("modal-championship-title").textContent = "Novo Campeonato";

    if (editId) {
        const c = allChampionships.find(item => item.id === editId);
        if (c) {
            document.getElementById("championship-id").value = c.id;
            document.getElementById("championship-name").value = c.nome;
            document.getElementById("championship-logo-url").value = c.logo_url || "";
            document.getElementById("championship-active").checked = !!c.ativo;
            document.getElementById("modal-championship-title").textContent = "Editar Campeonato";
        }
    }
    openModal("modal-championship");
}

window.editChampionship = function(id) {
    openChampionshipModal(id);
};

window.deleteChampionship = async function(id, name) {
    if (!confirm(`Deseja realmente deletar o campeonato "${name}"?`)) return;
    try {
        const res = await fetch(`/api/campeonatos/${id}`, { method: "DELETE" });
        if (res.ok) {
            showToast("Campeonato deletado com sucesso!", "success");
            loadChampionships();
        } else {
            showToast(await res.text(), "error");
        }
    } catch (err) {
        showToast("Erro ao deletar campeonato.", "error");
    }
};

// ==========================================
// PARTIDAS CRUD
// ==========================================
async function loadMatches() {
    try {
        const filterVal = document.getElementById("filter-match-championship").value;
        let url = "/api/public/partidas";
        if (filterVal) url += `?campeonato_id=${filterVal}`;
        
        const res = await fetch(url);
        if (res.ok) {
            allMatches = await res.json();
            renderMatchesList();
        }
    } catch (err) {
        console.error("Erro ao carregar partidas:", err);
    }
}

function renderMatchesList() {
    const tbody = document.getElementById("matches-list");
    if (!tbody) return;

    if (allMatches.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" style="text-align: center; padding: 2rem; color: var(--text-secondary);">Nenhuma partida cadastrada.</td></tr>';
        return;
    }

    tbody.innerHTML = allMatches.map(m => {
        const champ = allChampionships.find(c => c.id === m.campeonato_id);
        const champName = champ ? champ.nome : "Desconhecido";
        
        let scoreText = "-";
        if (m.gols_casa !== null && m.gols_fora !== null) {
            scoreText = `${m.gols_casa} x ${m.gols_fora}`;
        }
        const dateStr = m.data_jogo ? new Date(m.data_jogo).toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' }) : "Não agendado";
        
        return `
            <tr>
                <td style="font-weight: 600;">${champName}</td>
                <td>${m.rodada}</td>
                <td>
                    <div style="display: flex; flex-direction: column;">
                        <span>🏠 <b>${m.time_casa}</b></span>
                        <span>🚌 <b>${m.time_fora}</b></span>
                    </div>
                </td>
                <td style="font-weight: 800; font-size: 1.05rem; color: var(--accent-color);">${scoreText}</td>
                <td>
                    <span class="badge ${m.encerrada ? 'badge-success' : 'badge-warning'}">
                        ${m.encerrada ? 'Encerrada' : 'Em Andamento'}
                    </span>
                    <div style="font-size:0.7rem; color:var(--text-secondary); margin-top:0.25rem;">${dateStr}</div>
                </td>
                <td>
                    <div style="display:flex; gap:0.5rem;">
                        <button class="btn-icon" onclick="editMatch('${m.id}')" title="Editar"><i class="fa-solid fa-pen-to-square"></i></button>
                        <button class="btn-icon text-danger" onclick="deleteMatch('${m.id}')" title="Excluir"><i class="fa-solid fa-trash"></i></button>
                    </div>
                </td>
            </tr>
        `;
    }).join("");
}

async function openMatchModal(editId = null) {
    const form = document.getElementById("form-match");
    form.reset();
    document.getElementById("match-id").value = "";
    document.getElementById("modal-match-title").textContent = "Novo Jogo";

    if (editId) {
        const m = allMatches.find(item => item.id === editId);
        if (m) {
            document.getElementById("match-id").value = m.id;
            document.getElementById("match-championship").value = m.campeonato_id;
            document.getElementById("match-round").value = m.rodada;
            
            // Carrega times do campeonato e pré-seleciona os times da partida
            await updateMatchTeamsSelects(m.campeonato_id, m.time_casa, m.time_fora);
            
            document.getElementById("match-gols-home").value = m.gols_casa !== null ? m.gols_casa : "";
            document.getElementById("match-gols-away").value = m.gols_fora !== null ? m.gols_fora : "";
            document.getElementById("match-video").value = m.video_url || "";
            
            if (m.data_jogo) {
                const d = new Date(m.data_jogo);
                const localISO = new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
                document.getElementById("match-date").value = localISO;
            }
            document.getElementById("match-ended").checked = !!m.encerrada;
            document.getElementById("modal-match-title").textContent = "Editar Jogo";
        }
    } else {
        // Reseta os selects de times para novo jogo
        document.getElementById("match-home").innerHTML = '<option value="">Selecione o time...</option>';
        document.getElementById("match-away").innerHTML = '<option value="">Selecione o time...</option>';
    }
    openModal("modal-match");
}

window.editMatch = async function(id) {
    await openMatchModal(id);
};

window.deleteMatch = async function(id) {
    if (!confirm("Deseja realmente excluir esta partida?")) return;
    try {
        const res = await fetch(`/api/partidas/${id}`, { method: "DELETE" });
        if (res.ok) {
            showToast("Partida excluída!", "success");
            loadMatches();
        } else {
            showToast(await res.text(), "error");
        }
    } catch (err) {
        showToast("Erro ao excluir partida.", "error");
    }
};

// ==========================================
// JOGADORES DA LIGA (ESTATÍSTICAS) CRUD
// ==========================================
async function loadLeaguePlayers() {
    try {
        const filterVal = document.getElementById("filter-league-player-championship").value;
        let url = "/api/public/jogadores_liga";
        if (filterVal) url += `?campeonato_id=${filterVal}`;

        const res = await fetch(url);
        if (res.ok) {
            allLeaguePlayers = await res.json();
            renderLeaguePlayersList();
        }
    } catch (err) {
        console.error("Erro ao carregar jogadores da liga:", err);
    }
}

function renderLeaguePlayersList() {
    const tbody = document.getElementById("league-players-list");
    if (!tbody) return;

    if (allLeaguePlayers.length === 0) {
        tbody.innerHTML = '<tr><td colspan="7" style="text-align: center; padding: 2rem; color: var(--text-secondary);">Nenhum jogador cadastrado.</td></tr>';
        return;
    }

    tbody.innerHTML = allLeaguePlayers.map(p => {
        return `
            <tr>
                <td style="font-weight: 600; color: var(--text-primary);">${p.nome}</td>
                <td><b>${p.time}</b></td>
                <td>${p.jogos}</td>
                <td style="font-weight: 800; color: var(--accent-color); font-size:1.05rem;">${p.gols}</td>
                <td style="font-weight: 800; color: var(--text-primary);">${p.assistencias}</td>
                <td style="font-weight: 800; color: #f59e0b;">${p.nota_media.toFixed(2)}</td>
                <td>
                    <div style="display:flex; gap:0.5rem;">
                        <button class="btn-icon" onclick="editLeaguePlayer('${p.id}')" title="Editar"><i class="fa-solid fa-pen-to-square"></i></button>
                        <button class="btn-icon text-danger" onclick="deleteLeaguePlayer('${p.id}', '${p.nome}')" title="Excluir"><i class="fa-solid fa-trash"></i></button>
                    </div>
                </td>
            </tr>
        `;
    }).join("");
}

function openLeaguePlayerModal(editId = null) {
    const form = document.getElementById("form-league-player");
    form.reset();
    document.getElementById("league-player-id").value = "";
    document.getElementById("modal-league-player-title").textContent = "Novo Jogador";

    if (editId) {
        const p = allLeaguePlayers.find(item => item.id === editId);
        if (p) {
            document.getElementById("league-player-id").value = p.id;
            document.getElementById("league-player-championship").value = p.campeonato_id;
            document.getElementById("league-player-name").value = p.nome;
            document.getElementById("league-player-team").value = p.time;
            document.getElementById("league-player-matches").value = p.jogos;
            document.getElementById("league-player-goals").value = p.gols;
            document.getElementById("league-player-assists").value = p.assistencias;
            document.getElementById("league-player-rating").value = p.nota_media;
            document.getElementById("modal-league-player-title").textContent = "Editar Jogador";
        }
    }
    openModal("modal-league-player");
}

window.editLeaguePlayer = function(id) {
    openLeaguePlayerModal(id);
};

window.deleteLeaguePlayer = async function(id, name) {
    if (!confirm(`Deseja excluir as estatísticas de "${name}"?`)) return;
    try {
        const res = await fetch(`/api/jogadores_liga/${id}`, { method: "DELETE" });
        if (res.ok) {
            showToast("Jogador excluído com sucesso!", "success");
            loadLeaguePlayers();
        } else {
            showToast(await res.text(), "error");
        }
    } catch (err) {
        showToast("Erro ao excluir jogador.", "error");
    }
};

// ==========================================
// NOTÍCIAS CRUD
// ==========================================
async function loadNews() {
    try {
        const res = await fetch("/api/public/noticias");
        if (res.ok) {
            allNews = await res.json();
            renderNewsList();
        }
    } catch (err) {
        console.error("Erro ao carregar notícias:", err);
    }
}

function renderNewsList() {
    const listContainer = document.getElementById("news-list");
    if (!listContainer) return;

    if (allNews.length === 0) {
        listContainer.innerHTML = '<div class="no-data-card glass">Nenhuma notícia publicada ainda.</div>';
        return;
    }

    listContainer.innerHTML = allNews.map(n => {
        const cover = n.imagem_url || "https://i.ibb.co/C5B7BBjS/image.png";
        const dateStr = n.data_publicacao ? new Date(n.data_publicacao).toLocaleDateString('pt-BR', { dateStyle: 'long' }) : "";
        return `
            <div class="col-card glass" style="display:flex; flex-direction:column; padding:0; overflow:hidden;">
                <img src="${cover}" alt="${n.titulo}" style="width:100%; height:140px; object-fit:cover;" onerror="this.src='https://i.ibb.co/C5B7BBjS/image.png'">
                <div style="padding:1.25rem; flex:1; display:flex; flex-direction:column; gap:0.5rem;">
                    <div style="font-size:0.75rem; color:var(--text-secondary);">${dateStr}</div>
                    <h4 style="font-weight:600; font-size:1.1rem; line-height:1.3;">${n.titulo}</h4>
                    <p style="font-size:0.85rem; color:var(--text-secondary); line-height:1.4; display:-webkit-box; -webkit-line-clamp:3; -webkit-box-orient:vertical; overflow:hidden;">
                        ${n.subtitulo || n.conteudo}
                    </p>
                    <div style="margin-top:auto; display:flex; justify-content:flex-end; gap:0.5rem; padding-top:0.75rem; border-top:1px solid rgba(255,255,255,0.04);">
                        <button class="btn-icon" onclick="editNews('${n.id}')" title="Editar"><i class="fa-solid fa-pen-to-square"></i></button>
                        <button class="btn-icon text-danger" onclick="deleteNews('${n.id}', '${n.titulo}')" title="Deletar"><i class="fa-solid fa-trash"></i></button>
                    </div>
                </div>
            </div>
        `;
    }).join("");
}

function openNewsModal(editId = null) {
    const form = document.getElementById("form-news");
    form.reset();
    document.getElementById("news-id").value = "";
    document.getElementById("modal-news-title").textContent = "Nova Notícia";

    if (editId) {
        const n = allNews.find(item => item.id === editId);
        if (n) {
            document.getElementById("news-id").value = n.id;
            document.getElementById("news-title").value = n.titulo;
            document.getElementById("news-subtitle").value = n.subtitulo || "";
            document.getElementById("news-image-url").value = n.imagem_url || "";
            document.getElementById("news-content").value = n.conteudo;
            document.getElementById("modal-news-title").textContent = "Editar Notícia";
        }
    }
    openModal("modal-news");
}

window.editNews = function(id) {
    openNewsModal(id);
};

window.deleteNews = async function(id, title) {
    if (!confirm(`Deseja realmente deletar a notícia "${title}"?`)) return;
    try {
        const res = await fetch(`/api/noticias/${id}`, { method: "DELETE" });
        if (res.ok) {
            showToast("Notícia deletada com sucesso!", "success");
            loadNews();
        } else {
            showToast(await res.text(), "error");
        }
    } catch (err) {
        showToast("Erro ao deletar notícia.", "error");
    }
};

// ==========================================
// SISTEMA DE NOTIFICAÇÕES (TOAST)
// ==========================================
function showToast(message, type = "info") {
    const container = document.getElementById("toast-container");
    if (!container) return;
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
    
    setTimeout(() => {
        toast.style.animation = "slideIn 0.3s reverse forwards";
        toast.addEventListener("animationend", () => {
            toast.remove();
        });
    }, 4000);
}


// ==========================================
// ESTRUTURAS AUXILIARES PARA TIMES DO CAMPEONATO
// ==========================================

async function updateMatchTeamsSelects(campId, selectedHome = "", selectedAway = "") {
    const homeSelect = document.getElementById("match-home");
    const awaySelect = document.getElementById("match-away");
    
    if (!homeSelect || !awaySelect) return;
    
    homeSelect.innerHTML = '<option value="">Selecione o time...</option>';
    awaySelect.innerHTML = '<option value="">Selecione o time...</option>';
    
    if (!campId) return;
    
    try {
        const res = await fetch(`/api/public/campeonatos/${campId}/times`);
        if (res.ok) {
            const times = await res.json();
            if (times.length === 0) {
                homeSelect.innerHTML = '<option value="">Nenhum time cadastrado neste campeonato</option>';
                awaySelect.innerHTML = '<option value="">Nenhum time cadastrado neste campeonato</option>';
                return;
            }
            
            const options = times.map(t => `<option value="${t.nome}">${t.nome}</option>`).join("");
            
            homeSelect.innerHTML = '<option value="">Selecione o time...</option>' + options;
            awaySelect.innerHTML = '<option value="">Selecione o time...</option>' + options;
            
            if (selectedHome) homeSelect.value = selectedHome;
            if (selectedAway) awaySelect.value = selectedAway;
        }
    } catch (err) {
        console.error("Erro ao carregar times da partida:", err);
    }
}

window.openChampionshipTeamsModal = async function(campId, campNome) {
    document.getElementById("teams-camp-id").value = campId;
    document.getElementById("modal-teams-title").textContent = `Times — ${campNome}`;
    document.getElementById("new-team-name").value = "";
    
    openModal("modal-teams");
    await loadChampionshipTeams(campId);
};

async function loadChampionshipTeams(campId) {
    const list = document.getElementById("teams-list");
    if (!list) return;
    
    list.innerHTML = '<li style="color: var(--text-muted); text-align: center; padding: 1rem 0;">Carregando times...</li>';
    
    try {
        const res = await fetch(`/api/public/campeonatos/${campId}/times`);
        if (res.ok) {
            const times = await res.json();
            if (times.length === 0) {
                list.innerHTML = '<li style="color: var(--text-muted); text-align: center; padding: 1rem 0;">Nenhum time cadastrado neste campeonato.</li>';
                return;
            }
            
            list.innerHTML = times.map(t => `
                <li style="display:flex; justify-content:space-between; align-items:center; background:rgba(255,255,255,0.03); padding:0.6rem 0.8rem; border-radius:8px; border:1px solid var(--border-card); margin-bottom: 0.5rem;">
                    <span style="font-weight:600; color: #fff;">${t.nome}</span>
                    <button class="btn-icon text-danger" onclick="deleteChampionshipTeam('${t.id}', '${campId}', '${t.nome}')" style="padding:0.25rem; border:none; background:none;"><i class="fa-solid fa-trash"></i></button>
                </li>
            `).join("");
        } else {
            list.innerHTML = '<li style="color: var(--color-red); text-align: center; padding: 1rem 0;">Erro ao carregar times.</li>';
        }
    } catch (err) {
        console.error("Erro ao obter times:", err);
        list.innerHTML = '<li style="color: var(--color-red); text-align: center; padding: 1rem 0;">Erro de conexão.</li>';
    }
}

window.deleteChampionshipTeam = async function(timeId, campId, nome) {
    if (!confirm(`Deseja realmente excluir o time "${nome}"?`)) return;
    try {
        const res = await fetch(`/api/times/${timeId}`, { method: "DELETE" });
        if (res.ok) {
            showToast("Time removido com sucesso!", "success");
            await loadChampionshipTeams(campId);
        } else {
            showToast(await res.text(), "error");
        }
    } catch (err) {
        showToast("Erro ao excluir time.", "error");
    }
};
