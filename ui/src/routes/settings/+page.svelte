<script lang="ts">
	import { rpc, saveFile } from '#lib/api.ts';
	import Icon from '#lib/components/Icon.svelte';
	import Modal from '#lib/components/Modal.svelte';
	import RecoveryKey from '#lib/components/RecoveryKey.svelte';
	import { confirmAction } from '#lib/confirm.svelte.ts';
	import { money, shortDate } from '#lib/format.ts';
	import { session } from '#lib/session.svelte.ts';
	import { toasts } from '#lib/toast.svelte.ts';
	import type { Category, Rule, Settings } from '#lib/types.ts';

	let settings = $state<Settings | null>(null);
	let categories = $state<Category[]>([]);
	let rules = $state<Rule[]>([]);
	let demo = $derived(!!session.status?.demo);

	let passwordModal = $state(false);
	let recoveryModal = $state(false);
	let current = $state('');
	let next = $state('');
	let repeat = $state('');
	let newKey = $state('');
	let busy = $state(false);
	let modalError = $state('');

	let newCategory = $state({ name: '', kind: 'expense' as 'income' | 'expense', color: '#8a94a6' });
	let newRule = $state({ pattern: '', category_id: null as number | null });

	$effect(() => {
		void session.version;
		Promise.all([rpc<Settings>('get_settings'), rpc<Category[]>('list_categories'), rpc<Rule[]>('list_rules')])
			.then(([s, c, r]) => {
				settings = s;
				categories = c;
				rules = r;
			})
			.catch((e) => toasts.error(e));
	});

	async function update(patch: Partial<Settings>) {
		try {
			settings = await rpc<Settings>('update_settings', { patch });
			await session.refresh();
		} catch (err) {
			toasts.error(err);
		}
	}

	function closeModals() {
		passwordModal = recoveryModal = false;
		current = next = repeat = newKey = modalError = '';
	}

	async function changePassword(event: SubmitEvent) {
		event.preventDefault();
		if (next !== repeat) return (modalError = 'The two new passwords do not match');
		busy = true;
		try {
			await rpc('change_password', { current, new: next });
			toasts.show('Password changed');
			closeModals();
		} catch (err) {
			modalError = (err as Error).message;
		} finally {
			busy = false;
		}
	}

	async function rotateKey(event: SubmitEvent) {
		event.preventDefault();
		busy = true;
		try {
			newKey = (await rpc<{ recovery_key: string }>('rotate_recovery_key', { password: current })).recovery_key;
			modalError = '';
		} catch (err) {
			modalError = (err as Error).message;
		} finally {
			busy = false;
		}
	}

	async function backup() {
		try {
			const name = `coffer-backup-${new Date().toISOString().slice(0, 10)}.coffer`;
			const saved = await saveFile(
				name,
				(path) => rpc('backup_to_file', { path }),
				async () => {
					const b = await rpc<{ data: string }>('backup_bytes');
					return { content: b.data, base64: true };
				}
			);
			if (saved) toasts.show('Encrypted backup saved');
		} catch (err) {
			toasts.error(err);
		}
	}

	async function exportCsv(kind: 'transactions' | 'trades' | 'dividends') {
		const ok = await confirmAction({
			title: `Export ${kind} as CSV?`,
			message: 'The CSV file is not encrypted. Anyone who can open it can read it. Keep it somewhere private and delete it when you are done.',
			confirm: 'Export unencrypted file'
		});
		if (!ok) return;
		try {
			const name = `coffer-${kind}-${new Date().toISOString().slice(0, 10)}.csv`;
			const saved = await saveFile(
				name,
				(path) => rpc('export_to_file', { kind, path }),
				async () => ({ content: (await rpc<{ content: string }>('export_csv', { kind })).content })
			);
			if (saved) toasts.show('Export saved');
		} catch (err) {
			toasts.error(err);
		}
	}

	async function saveCategory(category: Partial<Category>) {
		try {
			await rpc('save_category', { category });
			session.changed();
		} catch (err) {
			toasts.error(err);
			session.changed();
		}
	}

	async function addCategory(event: SubmitEvent) {
		event.preventDefault();
		await saveCategory(newCategory);
		newCategory = { name: '', kind: newCategory.kind, color: '#8a94a6' };
	}

	async function deleteCategory(category: Category) {
		const ok = await confirmAction({
			title: `Delete ${category.name}?`,
			message: category.usage ? `${category.usage} transactions will become uncategorized, and rules pointing to it are removed.` : 'It is not used by any transaction.',
			confirm: 'Delete',
			danger: true
		});
		if (!ok) return;
		try {
			await rpc('delete_category', { id: category.id });
			session.changed();
		} catch (err) {
			toasts.error(err);
		}
	}

	async function addRule(event: SubmitEvent) {
		event.preventDefault();
		try {
			await rpc('save_rule', { rule: newRule });
			newRule = { pattern: '', category_id: newRule.category_id };
			session.changed();
		} catch (err) {
			toasts.error(err);
		}
	}

	async function deleteRule(rule: Rule) {
		try {
			await rpc('delete_rule', { id: rule.id });
			session.changed();
		} catch (err) {
			toasts.error(err);
		}
	}

	async function applyRules() {
		try {
			const count = await rpc<number>('apply_rules');
			toasts.show(count ? `Categorized ${count} transactions` : 'No uncategorized transaction matched a rule');
			session.changed();
		} catch (err) {
			toasts.error(err);
		}
	}
</script>

<div class="page narrow">
	<header class="page-head">
		<div>
			<h1>Settings</h1>
			<p>{demo ? 'You are exploring demo data: security and backup settings belong to a real vault.' : settings ? `Vault created ${shortDate(settings.created_at.slice(0, 10))}.` : ''}</p>
		</div>
	</header>

	{#if settings}
		<section class="card">
			<h2><Icon name="shield" size={17} /> Security</h2>
			<div class="setting">
				<div><strong>Lock automatically</strong><p class="muted">After this long without using Coffer, it locks and the password is needed again.</p></div>
				<select class="input short" value={settings.auto_lock_minutes} onchange={(e) => update({ auto_lock_minutes: Number((e.target as HTMLSelectElement).value) })}>
					{#each [1, 2, 5, 10, 15, 30, 60] as m (m)}<option value={m}>{m} {m === 1 ? 'minute' : 'minutes'}</option>{/each}
				</select>
			</div>
			<div class="setting">
				<div><strong>Master password</strong><p class="muted">Changing it does not re-encrypt your data, only the key that unlocks it.</p></div>
				<button class="btn" disabled={demo} onclick={() => (passwordModal = true)}>Change password</button>
			</div>
			<div class="setting">
				<div><strong>Recovery key</strong><p class="muted">Lost it? Create a new one: the old key stops working.</p></div>
				<button class="btn" disabled={demo} onclick={() => (recoveryModal = true)}>New recovery key</button>
			</div>
		</section>

		<section class="card">
			<h2><Icon name="download" size={17} /> Backup and export</h2>
			<div class="setting">
				<div><strong>Encrypted backup</strong><p class="muted">A copy of the vault, still encrypted. Safe to keep on a USB stick or in cloud storage. Restore it from the lock screen.</p></div>
				<button class="btn primary" disabled={demo} onclick={backup}>Save backup</button>
			</div>
			<div class="setting">
				<div><strong>Export to CSV</strong><p class="muted">For a spreadsheet or another app. <span class="warn-text">Exports are not encrypted.</span></p></div>
				<div class="actions">
					<button class="btn small" onclick={() => exportCsv('transactions')}>Transactions</button>
					<button class="btn small" onclick={() => exportCsv('trades')}>Trades</button>
					<button class="btn small" onclick={() => exportCsv('dividends')}>Dividends</button>
				</div>
			</div>
		</section>

		<section class="card">
			<h2><Icon name="refresh" size={17} /> Prices and network</h2>
			<div class="setting">
				<div>
					<strong>Offline mode</strong>
					<p class="muted">
						When on, Coffer never connects to the internet and you type prices by hand. When off, updating prices sends
						only the ticker symbols to Yahoo Finance and CoinGecko: no amounts, no accounts, nothing about you.
					</p>
				</div>
				<label class="switch">
					<input type="checkbox" checked={settings.offline_mode} onchange={(e) => update({ offline_mode: (e.target as HTMLInputElement).checked })} />
					<span></span>
				</label>
			</div>
			<div class="setting">
				<div><strong>Currency</strong><p class="muted">Every amount is shown in this currency. Nothing is converted, so record everything in it.</p></div>
				<select class="input short" value={settings.currency} onchange={(e) => update({ currency: (e.target as HTMLSelectElement).value })}>
					{#each ['EUR', 'USD', 'GBP', 'CHF'] as c (c)}<option>{c}</option>{/each}
				</select>
			</div>
		</section>

		<section class="card">
			<h2>Categories</h2>
			<table class="table">
				<thead><tr><th></th><th>Name</th><th>Type</th><th class="right">Monthly budget</th><th class="right">Used by</th><th></th></tr></thead>
				<tbody>
					{#each categories as c (c.id)}
						<tr>
							<td class="swatch"><input type="color" value={c.color} onchange={(e) => saveCategory({ ...c, color: (e.target as HTMLInputElement).value })} aria-label="Colour" /></td>
							<td><input class="input bare" value={c.name} onchange={(e) => saveCategory({ ...c, name: (e.target as HTMLInputElement).value })} aria-label="Name" /></td>
							<td class="muted">{c.kind === 'income' ? 'Income' : 'Spending'}</td>
							<td class="right num muted">{c.kind === 'expense' ? money(c.monthly_budget) : ''}</td>
							<td class="right num muted">{c.usage}</td>
							<td class="right"><button class="btn ghost small" onclick={() => deleteCategory(c)}>Delete</button></td>
						</tr>
					{/each}
				</tbody>
			</table>
			<form class="add" onsubmit={addCategory}>
				<input type="color" bind:value={newCategory.color} aria-label="Colour" />
				<input class="input" bind:value={newCategory.name} placeholder="New category" />
				<select class="input short" bind:value={newCategory.kind}>
					<option value="expense">Spending</option>
					<option value="income">Income</option>
				</select>
				<button class="btn" disabled={!newCategory.name.trim()}>Add</button>
			</form>
			<p class="faint hint">Budgets are set on the Budget page.</p>
		</section>

		<section class="card">
			<div class="card-head">
				<h2>Rules</h2>
				<button class="btn small" onclick={applyRules} disabled={!rules.length}>Apply to uncategorized</button>
			</div>
			<p class="muted">When a description contains the text, the transaction gets the category. Rules run on every import.</p>
			{#if rules.length}
				<table class="table">
					<tbody>
						{#each rules as r (r.id)}
							<tr>
								<td>Contains <code>{r.pattern}</code></td>
								<td><span class="pill"><i class="dot" style:background={r.category_color}></i>{r.category_name}</span></td>
								<td class="right"><button class="btn ghost small" onclick={() => deleteRule(r)}>Delete</button></td>
							</tr>
						{/each}
					</tbody>
				</table>
			{/if}
			<form class="add" onsubmit={addRule}>
				<input class="input" bind:value={newRule.pattern} placeholder="Text in the description, e.g. GREENMARKET" />
				<select class="input" bind:value={newRule.category_id}>
					<option value={null}>Category…</option>
					{#each categories as c (c.id)}<option value={c.id}>{c.name}</option>{/each}
				</select>
				<button class="btn" disabled={!newRule.pattern.trim() || !newRule.category_id}>Add rule</button>
			</form>
		</section>

		<section class="card about">
			<h2><Icon name="lock" size={17} /> How your data is protected</h2>
			<ul>
				<li>All data lives in one file on this device. There is no account, no server and no sync.</li>
				<li>The file is encrypted with AES-256-GCM. The key is random and is itself locked with your password, stretched with Argon2id (64 MB, 3 passes) to make guessing slow.</li>
				<li>While unlocked, data is held in memory only; nothing is written to disk unencrypted.</li>
				<li>The recovery key is a second, independent way to unlock the same key. Without the password or the recovery key, nobody can open the data, including the authors of this app.</li>
				<li>Coffer records and analyses; it never gives investment advice.</li>
			</ul>
		</section>
	{/if}
</div>

{#if passwordModal}
	<Modal title="Change master password" onclose={closeModals} width={440}>
		<form id="pw-form" class="grid" onsubmit={changePassword}>
			<label class="field"><span>Current password</span><input class="input" type="password" bind:value={current} autocomplete="current-password" /></label>
			<label class="field"><span>New password</span><input class="input" type="password" bind:value={next} autocomplete="new-password" /><small>At least 10 characters.</small></label>
			<label class="field"><span>Repeat new password</span><input class="input" type="password" bind:value={repeat} autocomplete="new-password" /></label>
			{#if modalError}<p class="error-text">{modalError}</p>{/if}
		</form>
		{#snippet footer()}
			<button class="btn" onclick={closeModals}>Cancel</button>
			<button class="btn primary" form="pw-form" disabled={busy || !current || next.length < 10}>Change password</button>
		{/snippet}
	</Modal>
{/if}

{#if recoveryModal}
	<Modal title={newKey ? 'New recovery key' : 'Create a new recovery key'} onclose={closeModals} width={480}>
		{#if newKey}
			<RecoveryKey value={newKey} onDone={closeModals} doneLabel="Done" />
		{:else}
			<form id="rk-form" class="grid" onsubmit={rotateKey}>
				<p class="muted">Your current recovery key will stop working. Confirm with your password.</p>
				<label class="field"><span>Master password</span><input class="input" type="password" bind:value={current} autocomplete="current-password" /></label>
				{#if modalError}<p class="error-text">{modalError}</p>{/if}
			</form>
		{/if}
		{#snippet footer()}
			{#if !newKey}
				<button class="btn" onclick={closeModals}>Cancel</button>
				<button class="btn primary" form="rk-form" disabled={busy || !current}>Create new key</button>
			{/if}
		{/snippet}
	</Modal>
{/if}

<style>
	.narrow {
		max-width: 920px;
	}

	section {
		margin-bottom: 16px;
	}

	section h2 {
		display: flex;
		align-items: center;
		gap: 9px;
		margin-bottom: 6px;
	}

	section h2 :global(svg) {
		color: var(--accent);
	}

	.setting {
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: 30px;
		padding: 14px 0;
		border-bottom: 1px solid var(--line);
	}

	.setting:last-child {
		border-bottom: 0;
	}

	.setting p {
		font-size: 13px;
		margin-top: 2px;
		max-width: 56ch;
	}

	.short {
		width: 150px;
		flex: none;
	}

	.warn-text {
		color: var(--warn);
	}

	.switch {
		position: relative;
		flex: none;
		width: 42px;
		height: 24px;
		cursor: pointer;
	}

	.switch input {
		opacity: 0;
		width: 0;
		height: 0;
	}

	.switch span {
		position: absolute;
		inset: 0;
		border-radius: 999px;
		background: var(--surface-3);
		border: 1px solid var(--line-strong);
		transition: background 0.15s;
	}

	.switch span::after {
		content: '';
		position: absolute;
		top: 2px;
		left: 2px;
		width: 18px;
		height: 18px;
		border-radius: 50%;
		background: var(--text);
		transition: transform 0.15s;
	}

	.switch input:checked + span {
		background: var(--accent);
		border-color: var(--accent);
	}

	.switch input:checked + span::after {
		transform: translateX(18px);
		background: var(--accent-ink);
	}

	.switch input:focus-visible + span {
		outline: 2px solid var(--focus);
		outline-offset: 2px;
	}

	.swatch {
		width: 40px;
	}

	input[type='color'] {
		width: 26px;
		height: 26px;
		padding: 0;
		border: 0;
		background: none;
		cursor: pointer;
	}

	.bare {
		border-color: transparent;
		background: transparent;
		height: 30px;
		padding: 0 6px;
	}

	.bare:hover {
		border-color: var(--line-strong);
	}

	.add {
		display: flex;
		gap: 8px;
		align-items: center;
		margin-top: 14px;
	}

	.hint {
		font-size: 12px;
		margin-top: 10px;
	}

	.about ul {
		margin: 10px 0 0;
		padding-left: 18px;
		color: var(--muted);
		display: grid;
		gap: 6px;
	}
</style>
