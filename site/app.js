/**
 * Khmer Menu Intelligence — browser recommender (skeleton).
 * Loads menus.json, parses free-text wants, enumerates combos per restaurant.
 */
(function () {
  'use strict';

  const LOG = (...args) => console.log('[menu-app]', ...args);
  const PARSE_PROMPT =
    'Extract structured order constraints from this user request. ' +
    'Return ONLY JSON: {"budget":number|null,"wants":[{"tag":string,"qty":number}]}. ' +
    'budget is null when the user gives none. ' +
    'tag is the food or drink in the user\'s own words, lowercase, e.g. chicken, vegetable, beer, papaya, squid, fried rice. ' +
    'Keep multi-word dishes together ("papaya salad" is one tag). ' +
    'qty: "a couple"/"two"=2, "a few"=3, else 1. Request:\n';

  let menusData = null;
  let allowCombinedDish = false;

  const el = {
    form: document.getElementById('query-form'),
    query: document.getElementById('query'),
    submit: document.getElementById('submit-btn'),
    badge: document.getElementById('parser-badge'),
    status: document.getElementById('status'),
    results: document.getElementById('results'),
    banner: document.getElementById('data-banner'),
  };

  function setDataBanner(data) {
    if (!el.banner) return;
    const meta = (data && data._meta) || {};
    const n = (data.restaurants || []).length;
    if (meta.dummy) {
      el.banner.textContent =
        'DUMMY DATA — menus.json is placeholder only. Real extraction not loaded yet.';
      el.banner.hidden = false;
    } else {
      el.banner.hidden = true;
    }
    LOG('setDataBanner', { dummy: !!meta.dummy, n, beer: meta.beer_available });
  }

  function money(n) {
    return '$' + Number(n).toFixed(2);
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  /** Regex fallback — always works offline. */
  function regexParse(text) {
    const t = String(text || '').toLowerCase();
    let budget = null;
    // "$10", "10$", "10 dollars", "10 usd"
    const dollar =
      t.match(/\$\s*(\d+(?:\.\d+)?)/) || t.match(/(\d+(?:\.\d+)?)\s*\$/);
    const dollarsWord = t.match(/(\d+(?:\.\d+)?)\s*(?:dollars?|usd)\b/);
    if (dollar) budget = parseFloat(dollar[1]);
    else if (dollarsWord) budget = parseFloat(dollarsWord[1]);
    else {
      const bare = t.match(/budget\s*(?:of\s*)?(\d+(?:\.\d+)?)/);
      if (bare) budget = parseFloat(bare[1]);
    }

    // Quantity words directly before a dish: "a couple of beers", "2 squid"
    function qtyBefore(tokens, idx) {
      const prev = tokens.slice(Math.max(0, idx - 3), idx).join(' ');
      if (/(couple|two|2)( of)?$/.test(prev) || /couple of$/.test(prev)) return 2;
      if (/(few|three|3)( of)?$/.test(prev)) return 3;
      const n = prev.match(/(\d+)$/);
      return n ? Math.max(1, parseInt(n[1], 10)) : 1;
    }

    // Runs of consecutive food words become one want: "fried squid", "papaya salad"
    const tokens = t.replace(/\$\s*\d+(?:\.\d+)?/g, ' ').match(/[a-z]+|\d+/g) || [];
    const wants = [];
    let run = [];
    let runStart = 0;
    const flush = () => {
      if (!run.length) return;
      const label = run.join(' ');
      if (!wants.some((w) => w.tag === label)) {
        wants.push({ tag: label, qty: qtyBefore(tokens, runStart) });
      }
      run = [];
    };
    tokens.forEach((tok, i) => {
      const term = foodTerm(tok);
      if (term) {
        if (!run.length) runStart = i;
        run.push(term);
      } else {
        flush();
      }
    });
    flush();

    LOG('regexParse', { budget, wants, text: t.slice(0, 80) });
    return { budget, wants };
  }

  // Everyday words that also appear in dish names; never treated as food.
  const STOPWORDS = new Set(
    ('i im me my we you a an the of and or but with without to for from in on at by ' +
      'is are be have has had want wants need would like get give find show order ' +
      'what which where should can could please some any about around under max ' +
      'budget dollar dollars usd riel riels couple few one two three four five ' +
      'much many more less cheap best good nice something food eat drink also ' +
      'this that there here it its set special house seller new small large big ' +
      'mix menu dish dishes plate')
      .split(' ')
  );

  // User words that should map onto a tag name.
  const SYNONYMS = {
    vegetables: 'vegetable', veg: 'vegetable', veggie: 'vegetable',
    veggies: 'vegetable', greens: 'vegetable', beers: 'beer',
    coke: 'soft_drink', soda: 'soft_drink', coffee: 'coffee_tea', tea: 'coffee_tea',
  };

  // Budget-only requests get a suggested meal built from these tag groups.
  const MEAL_GROUPS = {
    main: ['chicken', 'beef', 'pork', 'fish', 'seafood', 'duck'],
    side: ['vegetable', 'salad', 'soup'],
    drink: ['beer', 'soft_drink', 'water', 'coffee_tea'],
  };
  const SUGGESTED_MEAL = [
    { tag: 'main', qty: 1 },
    { tag: 'side', qty: 1 },
    { tag: 'drink', qty: 1 },
  ];

  let vocab = new Set();

  function singular(w) {
    if (w.endsWith('ies')) return w.slice(0, -3) + 'y';
    if (/(ch|sh|x|o)es$/.test(w)) return w.slice(0, -2);
    if (w.endsWith('s') && !w.endsWith('ss')) return w.slice(0, -1);
    return w;
  }

  /** Known food words: every tag plus every word in an English dish name. */
  function buildVocab(data) {
    const v = new Set();
    for (const r of data.restaurants || []) {
      for (const it of r.items || []) {
        for (const tag of it.tags || []) v.add(tag);
        for (const w of String(it.name_en || '').toLowerCase().match(/[a-z]+/g) || []) {
          if (w.length >= 3) {
            v.add(w);
            v.add(singular(w));
          }
        }
      }
    }
    for (const s of STOPWORDS) v.delete(s);
    LOG('buildVocab', { size: v.size });
    return v;
  }

  function foodTerm(tok) {
    if (STOPWORDS.has(tok) || /^\d+$/.test(tok)) return null;
    if (SYNONYMS[tok]) return SYNONYMS[tok];
    if (vocab.has(tok)) return tok;
    const s = singular(tok);
    return vocab.has(s) ? s : null;
  }

  async function parseQuery(text) {
    try {
      const ctrl = new AbortController();
      const timer = setTimeout(() => ctrl.abort(), 8000);
      LOG('parseQuery: trying /api/parse');
      const r = await fetch('/api/parse', {
        method: 'POST',
        signal: ctrl.signal,
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          model: 'openai/gpt-4o-mini',
          max_tokens: 300,
          messages: [
            {
              role: 'user',
              content:
                PARSE_PROMPT +
                text +
                '\nRespond with JSON only, no markdown.',
            },
          ],
        }),
      });
      clearTimeout(timer);
      if (!r.ok) throw new Error('parse status ' + r.status);
      const data = await r.json();
      const content =
        data.choices?.[0]?.message?.content ||
        data.content?.[0]?.text ||
        '';
      const cleaned = String(content)
        .replace(/^```(?:json)?\s*/i, '')
        .replace(/\s*```$/i, '')
        .trim();
      const parsed = JSON.parse(cleaned);
      if (
        (parsed.budget != null && typeof parsed.budget !== 'number') ||
        !Array.isArray(parsed.wants)
      ) {
        throw new Error('invalid LLM parse shape');
      }
      LOG('parseQuery: llm ok', parsed);
      return { budget: parsed.budget, wants: parsed.wants, parser: 'llm' };
    } catch (e) {
      LOG('parseQuery: fallback after', e.message || e);
      return { ...regexParse(text), parser: 'fallback' };
    }
  }

  /**
   * A want ("chicken", "papaya", "fried squid") matches an item when every
   * word is one of its tags or appears in its English / Khmer name.
   */
  function candidatesForTag(items, tag) {
    const terms = String(tag || '')
      .toLowerCase()
      .split(/\s+/)
      .filter(Boolean)
      .map((w) => SYNONYMS[w] || w);
    if (!terms.length) return [];
    const group = terms.length === 1 && MEAL_GROUPS[terms[0]];
    const res = terms.map(
      (w) =>
        new RegExp(
          '\\b' + singular(w).replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '(?:s|es)?\\b',
          'i'
        )
    );
    return items.filter((it) => {
      if (typeof it.price_usd !== 'number' || it.multi_unit !== false) return false;
      const tags = Array.isArray(it.tags) ? it.tags : [];
      const name = String(it.name_en || '');
      const km = String(it.name_km || '');
      if (group) return tags.some((t) => group.includes(t));
      return terms.every(
        (w, i) => tags.includes(w) || res[i].test(name) || (km && km.includes(w))
      );
    });
  }

  /**
   * Expand wants into picks: { item, qty, tag }[].
   * Same want qty can repeat one item; different wants use different rows
   * unless allowCombinedDish.
   * Missing tags are skipped so partial orders still surface (with missing noted).
   */
  function enumerateRestaurant(restaurant, wants, budget) {
    const items = restaurant.items || [];
    const allPools = wants.map((w) => ({
      tag: w.tag,
      qty: Math.max(1, w.qty | 0),
      cands: candidatesForTag(items, w.tag),
    }));
    const missing = allPools.filter((p) => !p.cands.length).map((p) => p.tag);
    const pools = allPools.filter((p) => p.cands.length);

    if (!pools.length) {
      LOG('enumerateRestaurant: nothing matched', {
        restaurant: restaurant.id,
        missing,
      });
      return { combos: [], missing };
    }

    if (missing.length) {
      LOG('enumerateRestaurant: partial match', {
        restaurant: restaurant.id,
        filled: pools.map((p) => p.tag),
        missing,
      });
    }

    const combos = [];

    function score(lines) {
      let total = 0;
      let unverified = 0;
      let minConf = 1;
      for (const line of lines) {
        total += line.item.price_usd * line.qty;
        if (!line.item.verified) unverified += 1;
        if (typeof line.item.confidence === 'number') {
          minConf = Math.min(minConf, line.item.confidence);
        }
      }
      return { total, unverified, minConf };
    }

    function dfs(idx, usedIds, lines) {
      if (idx === pools.length) {
        const s = score(lines);
        if (s.total <= budget + 1e-9) {
          combos.push({
            restaurantId: restaurant.id,
            restaurant: restaurant.restaurant,
            source_image: restaurant.source_image,
            lines: lines.map((l) => ({
              item: l.item,
              qty: l.qty,
              tag: l.tag,
              lineTotal: l.item.price_usd * l.qty,
            })),
            total: s.total,
            unverified: s.unverified,
            minConf: s.minConf,
            leftover: budget - s.total,
            missing: missing.slice(),
            filledCount: lines.length,
            wantCount: wants.length,
            partial: missing.length > 0,
          });
        }
        return;
      }

      const pool = pools[idx];
      for (const item of pool.cands) {
        if (!allowCombinedDish && usedIds.has(item.id)) continue;
        const nextUsed = new Set(usedIds);
        nextUsed.add(item.id);
        dfs(idx + 1, nextUsed, [
          ...lines,
          { item, qty: pool.qty, tag: pool.tag },
        ]);
      }
    }

    dfs(0, new Set(), []);
    return { combos, missing };
  }

  function hasBudget(constraints) {
    return constraints.budget != null && Number.isFinite(constraints.budget);
  }

  function recommend(constraints, data) {
    // No budget → search by availability only (cheapest first).
    const budget = hasBudget(constraints) ? constraints.budget : Infinity;
    // Budget but no dish named → suggest a main + side + drink per place.
    const suggested = !(constraints.wants || []).length && hasBudget(constraints);
    const wants = suggested ? SUGGESTED_MEAL : constraints.wants || [];
    const restaurants = data.restaurants || [];
    if (suggested) LOG('recommend: budget only, suggesting a meal');

    if (!wants.length) {
      LOG('recommend: no wants');
      return {
        ok: false,
        reason:
          'Tell me a budget or a dish (try “$10”, “papaya”, or “$10 chicken and beer”).',
        results: [],
        near: [],
        missing: [],
        partial: false,
      };
    }

    const allInBudget = [];
    const allOver = [];
    const missingAnywhere = new Set();

    for (const r of restaurants) {
      const { combos, missing } = enumerateRestaurant(r, wants, budget);
      for (const t of missing) missingAnywhere.add(t);

      // Cheapest combo over available tags (partial OK) for near-miss / over-budget
      const pools = wants
        .map((w) => ({
          tag: w.tag,
          qty: Math.max(1, w.qty | 0),
          cands: candidatesForTag(r.items || [], w.tag),
        }))
        .filter((p) => p.cands.length);
      if (pools.length) {
        const used = new Set();
        const lines = [];
        let skip = false;
        for (const p of pools) {
          const item = p.cands
            .slice()
            .sort((a, b) => a.price_usd - b.price_usd)
            .find((c) => allowCombinedDish || !used.has(c.id));
          if (!item) {
            skip = true;
            break;
          }
          used.add(item.id);
          lines.push({
            item,
            qty: p.qty,
            tag: p.tag,
            lineTotal: item.price_usd * p.qty,
          });
        }
        if (!skip && lines.length) {
          const total = lines.reduce((s, l) => s + l.lineTotal, 0);
          const unverified = lines.filter((l) => !l.item.verified).length;
          const minConf = Math.min(...lines.map((l) => l.item.confidence ?? 1));
          const miss = wants
            .map((w) => w.tag)
            .filter((t) => !lines.some((l) => l.tag === t));
          if (total > budget) {
            allOver.push({
              restaurantId: r.id,
              restaurant: r.restaurant,
              source_image: r.source_image,
              lines,
              total,
              unverified,
              minConf,
              leftover: budget - total,
              missing: miss,
              filledCount: lines.length,
              wantCount: wants.length,
              partial: miss.length > 0,
            });
          }
        }
      }

      allInBudget.push(...combos);
    }

    // Prefer complete orders, then more wants filled, then trust, then price
    allInBudget.sort((a, b) => {
      if (a.partial !== b.partial) return a.partial ? 1 : -1;
      if (b.filledCount !== a.filledCount) return b.filledCount - a.filledCount;
      if (a.unverified !== b.unverified) return a.unverified - b.unverified;
      if (b.minConf !== a.minConf) return b.minConf - a.minConf;
      return a.total - b.total;
    });

    // At most one per restaurant; top 3 for a budgeted order, more when
    // the user is just asking where a dish is available.
    const limit = hasBudget(constraints) ? 3 : 10;
    const seen = new Set();
    const top = [];
    for (const c of allInBudget) {
      if (seen.has(c.restaurantId)) continue;
      seen.add(c.restaurantId);
      top.push(c);
      if (top.length >= limit) break;
    }

    const anyPartial = top.some((t) => t.partial);
    const missingInTop = [
      ...new Set(top.flatMap((t) => t.missing || [])),
    ];

    LOG('recommend', {
      budget,
      wants,
      comboCount: allInBudget.length,
      top: top.map((t) => ({
        place: t.restaurant,
        total: t.total,
        partial: t.partial,
        missing: t.missing,
      })),
      missingAnywhere: [...missingAnywhere],
      missingInTop,
    });

    if (!top.length) {
      allOver.sort((a, b) => {
        if (a.partial !== b.partial) return a.partial ? 1 : -1;
        if (b.filledCount !== a.filledCount) return b.filledCount - a.filledCount;
        return a.total - b.total;
      });
      const near = [];
      const seenNear = new Set();
      for (const c of allOver) {
        if (seenNear.has(c.restaurantId)) continue;
        seenNear.add(c.restaurantId);
        near.push(c);
        if (near.length >= 3) break;
      }
      return {
        ok: false,
        reason: near.length
          ? 'Nothing fits your budget, but these places have what you asked for.'
          : 'No restaurant in the data lists ' +
            wants.map((w) => w.tag).join(', ') +
            '.',
        results: [],
        near,
        missing: suggested ? [] : [...missingAnywhere],
        partial: false,
      };
    }

    return {
      ok: true,
      results: top,
      near: [],
      missing: missingInTop,
      partial: anyPartial,
      suggested,
    };
  }

  function setBadge(parser) {
    el.badge.hidden = false;
    el.badge.textContent = 'parser: ' + parser;
    el.badge.classList.remove('llm', 'fallback');
    el.badge.classList.add(parser === 'llm' ? 'llm' : 'fallback');
  }

  function renderLines(combo) {
    return combo.lines
      .map((line) => {
        const it = line.item;
        let pills = '';
        if (it.verified) pills += '<span class="pill verified">verified</span>';
        if ((it.confidence ?? 1) < 0.75) {
          pills += '<span class="pill low">low confidence</span>';
        }
        return (
          '<li class="line">' +
          '<span class="tag">' +
          escapeHtml(line.tag) +
          '</span>' +
          '<div class="dish">' +
          '<span class="dish-km">' +
          escapeHtml(it.name_km) +
          '</span>' +
          (it.name_en
            ? '<span class="dish-en">' + escapeHtml(it.name_en) + '</span>'
            : '') +
          '<span class="price-raw">' +
          escapeHtml(it.price_raw) +
          ' each' +
          (line.qty > 1 ? ' · ×' + line.qty : '') +
          pills +
          '</span>' +
          '</div>' +
          '<span class="line-total">' +
          money(line.lineTotal) +
          '</span>' +
          '</li>'
        );
      })
      .join('');
  }

  function renderMissingList(missing) {
    if (!missing || !missing.length) return '';
    return (
      '<p class="missing-note">' +
      'Not on this menu: <strong>' +
      escapeHtml(missing.join(', ')) +
      '</strong>' +
      '</p>'
    );
  }

  function renderCombo(combo, budget, rank) {
    const capped = Number.isFinite(budget);
    const over = capped && combo.total > budget + 1e-9;
    const pct = budget > 0 ? Math.min(100, (combo.total / budget) * 100) : 100;
    const matched =
      combo.filledCount != null && combo.wantCount != null
        ? '<span class="match' +
          (combo.partial ? ' partial' : '') +
          '">' +
          combo.filledCount +
          ' of ' +
          combo.wantCount +
          ' items</span>'
        : '';
    return (
      '<article class="combo' +
      (combo.partial ? ' partial' : '') +
      '">' +
      '<header class="combo-head">' +
      '<span class="rank">' +
      rank +
      '</span>' +
      '<h2>' +
      escapeHtml(combo.restaurant) +
      '</h2>' +
      matched +
      '</header>' +
      renderMissingList(combo.missing) +
      '<ul class="lines">' +
      renderLines(combo) +
      '</ul>' +
      '<div class="totals' +
      (over ? ' over' : '') +
      '">' +
      '<div class="totals-row">' +
      '<span>Total</span>' +
      '<strong>' +
      money(combo.total) +
      '</strong>' +
      '</div>' +
      (capped
        ? '<div class="meter" aria-hidden="true"><span style="width:' +
          pct.toFixed(1) +
          '%"></span></div>' +
          '<div class="totals-sub">' +
          (over
            ? money(-combo.leftover) + ' over your ' + money(budget) + ' budget'
            : money(combo.leftover) + ' left of ' + money(budget)) +
          '</div>'
        : '') +
      '</div>' +
      '</article>'
    );
  }

  function renderRecommendation(rec, constraints) {
    const budget = hasBudget(constraints) ? constraints.budget : Infinity;
    let banner = '';
    if (rec.ok && rec.suggested) {
      banner =
        '<div class="partial-banner" role="status">' +
        '<strong>No dish named.</strong> Here is a suggested meal (main + side + drink) ' +
        'at each place within ' +
        money(budget) +
        '. Add a dish, like “chicken” or “squid”, to narrow it down.' +
        '</div>';
    } else if (rec.ok && rec.partial) {
      banner =
        '<div class="partial-banner" role="status">' +
        '<strong>Partial match.</strong> No single restaurant had every requested item. ' +
        'Showing the closest matches and marking what is missing' +
        (rec.missing && rec.missing.length
          ? ' (often: ' + escapeHtml(rec.missing.join(', ')) + ')'
          : '') +
        '.' +
        '</div>';
    }

    if (rec.ok) {
      el.results.innerHTML =
        banner +
        rec.results.map((c, i) => renderCombo(c, budget, i + 1)).join('');
      return;
    }

    let html =
      '<div class="empty"><p><strong>' +
      escapeHtml(rec.reason) +
      '</strong></p>';
    if (rec.missing && rec.missing.length) {
      html +=
        '<p class="missing-note"><strong>Often missing across menus:</strong> ' +
        escapeHtml(rec.missing.join(', ')) +
        '.</p>';
    }
    if (rec.near && rec.near.length) {
      html += '<p>Available, but over budget:</p>';
      html += rec.near
        .map((c, i) => renderCombo(c, budget, i + 1))
        .join('');
    }
    html += '</div>';
    el.results.innerHTML = html;
  }

  async function loadMenus() {
    LOG('loadMenus: fetching menus.json');
    const r = await fetch('menus.json', { cache: 'no-store' });
    if (!r.ok) throw new Error('menus.json ' + r.status);
    const data = await r.json();
    vocab = buildVocab(data);
    if (data._meta && data._meta.dummy) {
      LOG('loadMenus: DUMMY DATA loaded', {
        restaurants: (data.restaurants || []).length,
      });
    } else {
      LOG('loadMenus: loaded', {
        restaurants: (data.restaurants || []).length,
      });
    }
    return data;
  }

  async function onSubmit(ev) {
    ev.preventDefault();
    const text = el.query.value.trim();
    if (!text) return;

    el.submit.disabled = true;
    el.status.textContent = 'Parsing request…';
    el.results.innerHTML = '';
    el.badge.hidden = true;

    try {
      if (!menusData) {
        el.status.textContent = 'Loading menus…';
        menusData = await loadMenus();
      }

      const constraints = await parseQuery(text);
      setBadge(constraints.parser);
      LOG('constraints', constraints);

      const isDummy = !!(menusData._meta && menusData._meta.dummy);
      el.status.textContent =
        'Searching ' +
        (menusData.restaurants || []).length +
        (isDummy ? ' restaurants (dummy)…' : ' restaurants…');
      LOG('search', { isDummy, restaurants: (menusData.restaurants || []).length });

      const rec = recommend(constraints, menusData);
      renderRecommendation(rec, constraints);

      if (rec.ok) {
        const partialNote = rec.partial
          ? ' (partial — missing: ' +
            (rec.missing.length ? rec.missing.join(', ') : 'some items') +
            ')'
          : '';
        el.status.textContent = rec.suggested
          ? 'Suggested meals at ' +
            rec.results.length +
            ' restaurant(s) within ' +
            money(constraints.budget) +
            '.'
          : 'Found ' +
          rec.results.length +
          ' restaurant option(s)' +
          (hasBudget(constraints)
            ? ' within ' + money(constraints.budget)
            : ' (no budget given)') +
          partialNote +
          '.';
        LOG('submit ok', {
          partial: rec.partial,
          missing: rec.missing,
          n: rec.results.length,
        });
      } else {
        el.status.textContent = rec.reason;
        LOG('submit empty', { missing: rec.missing, near: rec.near.length });
      }
    } catch (e) {
      console.error('[menu-app] error', e);
      el.status.textContent = 'Error: ' + (e.message || e);
    } finally {
      el.submit.disabled = false;
    }
  }

  async function init() {
    LOG('init');
    el.form.addEventListener('submit', onSubmit);
    try {
      menusData = await loadMenus();
      setDataBanner(menusData);
      const isDummy = !!(menusData._meta && menusData._meta.dummy);
      const n = (menusData.restaurants || []).length;
      el.status.textContent = isDummy
        ? 'Ready — ' + n + ' dummy restaurants loaded. Submit to search.'
        : 'Ready — ' +
          n +
          ' restaurants loaded' +
          (menusData._meta && menusData._meta.sample_only ? ' (sample extract)' : '') +
          '. Submit to search.';
      LOG('init loaded', { isDummy, n, sample: !!(menusData._meta && menusData._meta.sample_only) });
    } catch (e) {
      console.error('[menu-app] load failed', e);
      if (el.banner) {
        el.banner.textContent =
          'Could not load menus.json — serve the site/ folder over HTTP.';
      }
      el.status.textContent =
        'Could not load menus.json. Serve this folder over HTTP (file:// fetch often fails).';
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
