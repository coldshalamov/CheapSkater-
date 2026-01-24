
document.addEventListener('DOMContentLoaded', () => {
  const dataEl = document.getElementById('group-data');
  const grid = document.getElementById('cards-grid');
  const sentinel = document.getElementById('scroll-sentinel');
  const searchInput = document.getElementById('search');
  const noResultsMessage = document.getElementById('no-results-message');
  const discountSelect = document.getElementById('discount_filter');
  const stockSelect = document.getElementById('stock_filter');
  const discountCustom = document.querySelector('.custom-range[data-target="discount"]');
  const stockCustom = document.querySelector('.custom-range[data-target="stock"]');
  const BATCH_SIZE = 30;
  const VISIBLE_STORE_LIMIT = 1;
  const toastEl = document.getElementById('saved-toast');
  let toastTimerId;

  const showToast = (message) => {
    if (!toastEl) {
      return;
    }
    toastEl.textContent = message;
    toastEl.hidden = false;
    toastEl.classList.add('visible');
    if (toastTimerId) {
      clearTimeout(toastTimerId);
    }
    toastTimerId = setTimeout(() => {
      toastEl.classList.remove('visible');
      toastEl.hidden = true;
    }, 3200);
  };

  if (!grid || !dataEl) {
    return;
  }

  const toggleCustomRange = (selectEl, container) => {
    if (!selectEl || !container) return;
    container.hidden = selectEl.value !== 'custom';
  };

  toggleCustomRange(discountSelect, discountCustom);
  toggleCustomRange(stockSelect, stockCustom);

  discountSelect?.addEventListener('change', () => {
    toggleCustomRange(discountSelect, discountCustom);
  });

  stockSelect?.addEventListener('change', () => {
    toggleCustomRange(stockSelect, stockCustom);
  });

  let allGroups = [];
  try {
    allGroups = JSON.parse(dataEl.textContent || '[]');
  } catch (err) {
    console.error('Failed to parse group data', err);
    return;
  }

  const formatCurrency = (value) => {
    if (value === null || value === undefined) return '';
    return `$${Number(value).toFixed(2)}`;
  };

  const formatDiscount = (group) => {
    if (group.min_pct_off === null || group.min_pct_off === undefined) return '';
    const minPct = Math.floor(group.min_pct_off * 100);
    if (group.max_pct_off !== null && group.max_pct_off !== undefined && group.max_pct_off !== group.min_pct_off) {
      const maxPct = Math.floor(group.max_pct_off * 100);
      return `${minPct}% - ${maxPct}% off`;
    }
    return `${minPct}% off`;
  };

  const formatDate = (value, { showTime = true } = {}) => {
    if (!value) return '';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return '';
    const opts = showTime
      ? { month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit' }
      : { month: 'short', day: '2-digit' };
    return date.toLocaleString(undefined, opts);
  };

  const formatRangeText = (minValue, maxValue, prefix) => {
    if (minValue === null || minValue === undefined) return '';
    const base = `${prefix} ${formatCurrency(minValue)}`;
    if (maxValue !== null && maxValue !== undefined && maxValue !== minValue) {
      return `${base} - ${formatCurrency(maxValue)}`;
    }
    return base;
  };

  const availabilityClass = (text) => {
    if (!text) return '';
    return `availability-${text.toLowerCase().replace(/\s+/g, '-')}`;
  };

  document.addEventListener('toggle', (event) => {
    const dropdown = event.target;
    if (!(dropdown instanceof HTMLElement)) {
      return;
    }
    if (!dropdown.classList.contains('store-dropdown')) {
      return;
    }
    const summary = dropdown.querySelector('summary');
    if (!summary) {
      return;
    }
    const collapsedText = summary.dataset.collapsedText || summary.textContent;
    const expandedText = summary.dataset.expandedText || collapsedText;
    summary.textContent = dropdown.open ? expandedText : collapsedText;
  });

  const renderStoreRow = (store = {}, defaultSku = '') => {
    const availability = store.availability || 'Unknown';
    const availabilityClassName = availabilityClass(availability);
    const storeName = store.store_label || store.store_name || (store.store_zip ? `Lowe's ${store.store_zip}` : (store.store_id ? `Store ${store.store_id}` : 'Unknown store'));
    const storeLink = store.store_product_url || store.product_url || '#';
    const storeTip = store.store_tooltip || `${store.store_city || ''}, ${store.store_state || ''} ${store.store_zip || ''}`;
    const savings = store.price_was !== null && store.price_was !== undefined && store.price !== null && store.price !== undefined
      ? Math.max(store.price_was - store.price, 0)
      : null;
    const savingsPct = store.price_was && store.price
      ? Math.floor(Math.max(store.price_was - store.price, 0) / store.price_was * 100)
      : null;
    const stockText = store.stock_estimate !== null && store.stock_estimate !== undefined
      ? `Stock: ${store.stock_estimate}`
      : (store.stock_label || '');
    const storeNumber = store.store_id || store.store_number || '';
    const sku = store.sku || defaultSku || '';
    const canSave = Boolean(storeNumber && sku);
    return `
      <div class="store-row">
        <div class="store-details">
          <div class="store-name" title="${storeTip}">${storeName}</div>
          <div class="store-location">
            ${(store.store_state || '')} ${store.store_zip || ''}
          </div>
        </div>
        <div class="store-pricing">
          <div class="price">${store.price !== null && store.price !== undefined ? formatCurrency(store.price) : '<span class="muted">-</span>'}</div>
          ${store.price_was ? `<div class="was-price">Was ${formatCurrency(store.price_was)}</div>` : ''}
          ${savings ? `<div class="store-savings">Save ${formatCurrency(savings)}</div>` : ''}
          ${savingsPct !== null ? `<div class="store-savings pct">${savingsPct}% off</div>` : ''}
          ${store.prev_price ? `<div class="prev-price">Prev ${formatCurrency(store.prev_price)}</div>` : ''}
        </div>
        <div class="store-meta">
          <span class="availability-badge ${availabilityClassName}">${availability}</span>
          ${stockText ? `<span class="stock-pill">${stockText}</span>` : ''}
          ${store.updated_at ? `<span class="timestamp">Updated ${formatDate(store.updated_at)}</span>` : ''}
        </div>
        <div class="store-action">
          <a class="btn small" href="${storeLink}" target="_blank" rel="noopener">View Store Deal</a>
          ${canSave ? `<button type="button" class="btn tertiary small js-save-deal" data-store="${storeNumber}" data-sku="${sku}">Save deal</button>` : ''}
        </div>
      </div>
    `;
  };

  const buildStoreRows = (stores = [], defaultSku = '') => {
    const preview = stores.slice(0, VISIBLE_STORE_LIMIT);
    const extras = stores.slice(VISIBLE_STORE_LIMIT);

    const previewMarkup = preview.map((store) => renderStoreRow(store, defaultSku)).join('');
    const extraMarkup = extras.map((store) => renderStoreRow(store, defaultSku)).join('');
    const dropdown = extras.length
      ? (() => {
          const hiddenCount = extras.length;
          const collapsedText = `Show ${hiddenCount} more store${hiddenCount === 1 ? '' : 's'}`;
          const expandedText = `Show ${hiddenCount} fewer store${hiddenCount === 1 ? '' : 's'}`;
          return `<details class="store-dropdown">
            <summary data-collapsed-text="${collapsedText}" data-expanded-text="${expandedText}">${collapsedText}</summary>
            <div class="store-dropdown__content">
              ${extraMarkup}
            </div>
          </details>`;
        })()
      : '';

    return `<div class="store-list">
      ${previewMarkup}
      ${dropdown}
    </div>`;
  };

  const buildCard = (group) => {
    const keywords = [
      group.title || '',
      group.sku || '',
      ...(group.stores || []).map((store) => `${store.store_name || ''} ${store.store_state || ''} ${store.store_zip || ''} ${store.store_id || ''}`),
    ]
      .join(' ')
      .toLowerCase();
    const discount = formatDiscount(group);
    const priceCurrent = group.min_price !== null && group.min_price !== undefined
       ? `${formatCurrency(group.min_price)}${group.max_price !== null && group.max_price !== undefined && group.max_price !== group.min_price ? ` - ${formatCurrency(group.max_price)}` : ''}` - ${formatCurrency(group.max_price)}` : ''}`
      : 'Price unavailable';
    const regularPrice = group.min_price_was !== null && group.min_price_was !== undefined
      ? formatRangeText(group.min_price_was, group.max_price_was, 'Was')
      : '';
    const priceSpread = group.price_spread !== null && group.price_spread !== undefined && group.price_spread > 0
      ? `Spread ${formatCurrency(group.price_spread)}`
      : '';
    const savingsText = group.min_savings !== null && group.min_savings !== undefined
      ? `Save ${formatCurrency(group.min_savings)}${group.max_savings !== null && group.max_savings !== undefined && group.max_savings !== group.min_savings ? ` - ${formatCurrency(group.max_savings)}` : ''}` - ${formatCurrency(group.max_savings)}` : ''}`
      : '';
    const storeCountText = `${group.locations} store${group.locations === 1 ? '' : 's'} with this price`;
    const addedAgo = Number.isFinite(group.days_since_added)
      ? `${group.days_since_added}d ago`
      : '';

    const card = document.createElement('article');
    card.className = 'product-card';
    card.dataset.keywords = keywords;
    card.innerHTML = `
      <div class="product-card__header">
        <div class="product-card__image">
          ${
            group.image_url
              ? `<img src="${group.image_url}" alt="${group.title}" loading="lazy" width="70" height="70" style="max-width:70px;max-height:70px;width:auto;height:auto;object-fit:contain;">`
              : '<div class="image-placeholder">No Image</div>'
          }
        </div>
        <div class="product-card__body">
          <h2 class="product-title">
            ${
              group.best_product_url
                ? `<a href="${group.best_product_url}" target="_blank" rel="noopener">${group.title}</a>`
                : group.title
            }
          </h2>
          <div class="product-meta">
            <span class="pill category">${group.category || 'Uncategorised'}</span>
            <span class="pill sku">SKU ${group.sku}</span>
            <span class="pill locations">${group.locations} store${group.locations === 1 ? '' : 's'}</span>
          </div>
          <div class="product-pricing">
            <div class="price-current">${priceCurrent}</div>
            ${regularPrice ? `<div class="price-was">${regularPrice}</div>` : ''}
            ${priceSpread ? `<div class="price-spread">${priceSpread}</div>` : ''}
            ${savingsText ? `<div class="price-savings">${savingsText}</div>` : ''}
            ${discount ? `<span class="discount-badge">${discount}</span>` : ''}
            <div class="store-count-note">${storeCountText}</div>
          </div>
          <div class="product-timeline">
            ${group.added_at ? `<span>Added ${formatDate(group.added_at, { showTime: false })}${addedAgo ? ` (${addedAgo})` : ''}</span>` : ''}
            ${group.last_seen ? `<span>Updated ${formatDate(group.last_seen)}</span>` : ''}
          </div>
        </div>
      </div>
      <div class="store-list">
        ${buildStoreRows(group.stores, group.sku || '')}
      </div>
    `;
    return card;
  };

  let filteredGroups = allGroups.slice();
  let renderedCount = parseInt(grid.dataset.initialCount || '0', 10) || 0;

  const renderBatch = (reset = false) => {
    if (reset) {
      grid.innerHTML = '';
      renderedCount = 0;
    }
    if (renderedCount >= filteredGroups.length) {
      if (filteredGroups.length === 0) {
        noResultsMessage.hidden = false;
      } else {
        noResultsMessage.hidden = true;
      }
      return;
    }
    const slice = filteredGroups.slice(renderedCount, renderedCount + BATCH_SIZE);
    slice.forEach((group) => grid.appendChild(buildCard(group)));
    renderedCount += slice.length;

    if (filteredGroups.length === 0) {
      noResultsMessage.hidden = false;
    } else {
      noResultsMessage.hidden = true;
    }
  };

  const handleSearch = () => {
    const query = (searchInput?.value || '').trim().toLowerCase();
    if (!query) {
      filteredGroups = allGroups.slice();
    } else {
      filteredGroups = allGroups.filter((group) => {
        const keywords = [
          group.title || '',
          group.sku || '',
          ...(group.stores || []).map((store) => `${store.store_name || ''} ${store.store_state || ''} ${store.store_zip || ''}`),
        ]
          .join(' ')
          .toLowerCase();
        return keywords.includes(query);
      });
    }
    renderBatch(true);
  };

  const saveDealRequest = async (storeNumber, sku) => {
    const response = await fetch('/cheapskater/save-deal', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ store_number: storeNumber, sku }),
    });
    if (!response.ok) {
      throw new Error(`Save failed with status ${response.status}`);
    }
    return response.json();
  };

  const handleSaveButton = async (button) => {
    const storeNumber = button.dataset.store;
    const sku = button.dataset.sku;
    if (!storeNumber || !sku) {
      return;
    }
    const originalText = button.textContent;
    button.disabled = true;
    try {
      const payload = await saveDealRequest(storeNumber, sku);
      if (!payload?.ok) {
        throw new Error('Invalid save response');
      }
      button.textContent = 'Saved';
      button.classList.add('saved');
      button.setAttribute('aria-pressed', 'true');
      showToast('Deal saved. Open Saved Deals to review your stops.');
    } catch (error) {
      console.error('Unable to save deal', error);
      button.textContent = 'Retry';
      setTimeout(() => {
        button.textContent = originalText;
      }, 1800);
    } finally {
      button.disabled = false;
    }
  };

  grid.addEventListener('click', (event) => {
    const saveButton = event.target.closest('.js-save-deal');
    if (!saveButton) {
      return;
    }
    event.preventDefault();
    handleSaveButton(saveButton);
  });

  const observer = new IntersectionObserver(
    (entries) => {
      const [entry] = entries;
      if (entry.isIntersecting) {
        renderBatch();
      }
    },
    {
      rootMargin: '200px',
    }
  );

  if (sentinel) {
    observer.observe(sentinel);
  }

  if (searchInput) {
    searchInput.addEventListener('input', () => {
      handleSearch();
    });
  }

  if (renderedCount === 0) {
    renderBatch(true);
  }
});
