// ========== УПРАВЛЕНИЕ МОДАЛЬНЫМ ОКНОМ ЧАТА ==========
function openChat() {
    document.getElementById('chatModal').style.display = 'flex';
}

function closeChat() {
    document.getElementById('chatModal').style.display = 'none';
}

window.onclick = function(event) {
    const modal = document.getElementById('chatModal');
    if (event.target === modal) {
        modal.style.display = 'none';
    }
}

// ========== ФИЛЬТРЫ И ОТОБРАЖЕНИЕ ТОВАРОВ ==========
// Данные товаров
const products = [
    { id: 1, name: "Turbo SYN Gasoline 5W-30", brand: "Hydundai-KIA", original: "ОРИГИНАЛ", sku: "0510000441", type: "синтетика", viscosity: "5W-30", price: "4 925 ₽", delivery: "от 12 до 24 часов", image: "🛢️", bgGradient: "linear-gradient(135deg, #667eea 0%, #764ba2 100%)" },
    { id: 2, name: "GENESIS ARMORTECH SO 5W-40", brand: "LUKOIL", original: "ОРИГИНАЛ", sku: "2255948", type: "синтетика", viscosity: "5W-40", price: "2 670 ₽", delivery: "от 24 до 48 часов", image: "🔧", bgGradient: "linear-gradient(135deg, #f093fb 0%, #f5576c 100%)" },
    { id: 3, name: "SP GF-6A 5W-30", brand: "LUKOIL", original: "ОРИГИНАЛ", sku: "0888013705", type: "синтетика", viscosity: "5W-30", price: "4 420 ₽", delivery: "от 12 до 24 часов", image: "⚙️", bgGradient: "linear-gradient(135deg, #4facfe 0%, #00f2fe 100%)" },
    { id: 4, name: "GENESIS ARMORTECH FD 5W-30", brand: "LUKOIL", original: "ОРИГИНАЛ", sku: "3149878", type: "синтетика", viscosity: "5W-30", price: "2 750 ₽", delivery: "от 12 до 24 часов", image: "🏎️", bgGradient: "linear-gradient(135deg, #43e97b 0%, #38f9d7 100%)" },
    { id: 5, name: "Dexos 2 5W-30", brand: "GENERAL MOTORS", original: "ОРИГИНАЛ", sku: "93165557", type: "синтетика", viscosity: "5W-30", price: "3 750 ₽", delivery: "2 дня", image: "🚗", bgGradient: "linear-gradient(135deg, #fa709a 0%, #fee140 100%)" },
    { id: 6, name: "GENESIS UNIVERSAL 10W-40", brand: "LUKOIL", original: "ОРИГИНАЛ", sku: "3148646", type: "полусинтетика", viscosity: "10W-40", price: "1 470 ₽", delivery: "2 дня", image: "🔩", bgGradient: "linear-gradient(135deg, #a8edea 0%, #fed6e3 100%)" },
    { id: 7, name: "Ravenol HCL 5W-30", brand: "Ravenol", original: "ОРИГИНАЛ", sku: "R1234567", type: "синтетика", viscosity: "5W-30", price: "6 300 ₽", delivery: "от 12 до 24 часов", image: "🏁", bgGradient: "linear-gradient(135deg, #ff9a9e 0%, #fecfef 100%)" },
    { id: 8, name: "Castrol Edge 5W-30", brand: "Castrol", original: "ОРИГИНАЛ", sku: "C8765432", type: "синтетика", viscosity: "5W-30", price: "4 400 ₽", delivery: "от 12 до 24 часов", image: "🛞", bgGradient: "linear-gradient(135deg, #a1c4fd 0%, #c2e9fb 100%)" }
];

// Функция получения цвета бренда
function getBrandColor(brand) {
    const colors = {
        'LUKOIL': 'linear-gradient(135deg, #ff6b35 0%, #e55a2b 100%)',
        'Hydundai-KIA': 'linear-gradient(135deg, #1a3c6c 0%, #0e2a4a 100%)',
        'GENERAL MOTORS': 'linear-gradient(135deg, #2c3e50 0%, #1a252f 100%)',
        'Ravenol': 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
        'Castrol': 'linear-gradient(135deg, #f093fb 0%, #f5576c 100%)',
        'Mobil': 'linear-gradient(135deg, #4facfe 0%, #00f2fe 100%)',
        'TOYOTA': 'linear-gradient(135deg, #43e97b 0%, #38f9d7 100%)',
        'SHELL': 'linear-gradient(135deg, #fa709a 0%, #fee140 100%)'
    };
    return colors[brand] || 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)';
}

// Функция отображения товаров
function renderProducts() {
    const container = document.getElementById('productsContainer');
    if (!container) return;
    container.innerHTML = '';
    
    const selectedBrands = Array.from(document.querySelectorAll('.brand-filter:checked')).map(cb => cb.parentElement.textContent.trim());
    const selectedViscosity = Array.from(document.querySelectorAll('.viscosity-filter:checked')).map(cb => cb.parentElement.textContent.trim());
    const selectedTypes = Array.from(document.querySelectorAll('.type-filter:checked')).map(cb => cb.parentElement.textContent.trim());

    let filtered = products;
    if (selectedBrands.length) filtered = filtered.filter(p => selectedBrands.includes(p.brand));
    if (selectedViscosity.length) filtered = filtered.filter(p => selectedViscosity.includes(p.viscosity));
    if (selectedTypes.length) filtered = filtered.filter(p => selectedTypes.includes(p.type));

    if (filtered.length === 0) {
        container.innerHTML = '<div style="grid-column:1/-1; text-align:center; padding:40px;">😞 Товары не найдены. Попробуйте изменить фильтры.</div>';
        return;
    }

    filtered.forEach(product => {
        const card = document.createElement('div');
        card.className = 'product-card';
        card.innerHTML = `
            <div class="product-image" style="background: ${getBrandColor(product.brand)}; background-image: url('/static/images/${product.sku}.jpg'); background-size: contain; background-position: center; background-repeat: no-repeat;">
            </div>
            <div class="product-brand">${product.brand}</div>
            <div class="product-original">${product.original}</div>
            <div class="product-sku">${product.sku}</div>
            <div class="product-name">${product.name}</div>
            <div class="product-specs">${product.type} ${product.viscosity} 4 л.</div>
            <div class="product-price">${product.price}</div>
            <div class="product-delivery">🚚 ${product.delivery}</div>
            <button class="cart-btn" onclick="alert('Товар ${product.sku} добавлен в корзину!')">В корзину</button>
        `;
        container.appendChild(card);
    });
}

// Функция поиска
function searchParts() {
    const searchInput = document.getElementById('searchInput');
    if (!searchInput) return;
    const query = searchInput.value.toLowerCase().trim();
    if (!query) {
        renderProducts();
        return;
    }
    
    const container = document.getElementById('productsContainer');
    if (!container) return;
    const filtered = products.filter(p => 
        p.name.toLowerCase().includes(query) || 
        p.sku.toLowerCase().includes(query) ||
        p.brand.toLowerCase().includes(query)
    );
    
    if (filtered.length === 0) {
        container.innerHTML = '<div style="grid-column:1/-1; text-align:center; padding:40px;">😞 По вашему запросу ничего не найдено.</div>';
        return;
    }
    
    container.innerHTML = '';
    filtered.forEach(product => {
        const card = document.createElement('div');
        card.className = 'product-card';
        card.innerHTML = `
            <div class="product-image" style="background: ${getBrandColor(product.brand)}; display: flex; align-items: center; justify-content: center;">
                <span style="font-size: 64px;">${product.image}</span>
            </div>
            <div class="product-brand">${product.brand}</div>
            <div class="product-original">${product.original}</div>
            <div class="product-sku">${product.sku}</div>
            <div class="product-name">${product.name}</div>
            <div class="product-specs">${product.type} ${product.viscosity} 4 л.</div>
            <div class="product-price">${product.price}</div>
            <div class="product-delivery">🚚 Срок: ${product.delivery}</div>
            <button class="cart-btn" onclick="alert('Товар ${product.sku} добавлен в корзину!')">В корзину</button>
        `;
        container.appendChild(card);
    });
}

// Инициализация фильтров и товаров при загрузке страницы
document.addEventListener('DOMContentLoaded', function() {
    // Назначаем обработчики фильтрам
    document.querySelectorAll('.brand-filter, .viscosity-filter, .type-filter').forEach(checkbox => {
        checkbox.addEventListener('change', renderProducts);
    });
    
    // Отображаем товары
    renderProducts();
});