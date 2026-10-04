<script lang="ts">
	import { goto } from '$app/navigation';
	import { readFileText, rpc } from '#lib/api.ts';
	import Icon from '#lib/components/Icon.svelte';
	import { resetTxFilters } from '#lib/filters.svelte.ts';
	import { money, shortDate } from '#lib/format.ts';
	import { session } from '#lib/session.svelte.ts';
	import { toasts } from '#lib/toast.svelte.ts';
	import type { Account, ImportInspection, ImportMapping, ImportPreview } from '#lib/types.ts';

	let mode = $state<'bank' | 'trades'>('bank');
	let accounts = $state<Account[]>([]);
	let accountId = $state<number | null>(null);
	let fileName = $state('');
	let content = $state('');
	let inspection = $state<ImportInspection | null>(null);
	let mapping = $state<ImportMapping | null>(null);
	let preview = $state<ImportPreview | null>(null);
	let previewError = $state('');
	let busy = $state(false);
	let result = $state<string | null>(null);

	$effect(() => {
		void session.version;
		rpc<Account[]>('list_accounts').then((a) => {
			accounts = a.filter((x) => !x.archived);
			if (!accountId || !accounts.some((x) => x.id === accountId)) accountId = pick(mode);
		});
	});

	function pick(m: typeof mode) {
		const list = m === 'trades' ? accounts.filter((a) => a.kind === 'brokerage') : accounts.filter((a) => a.kind !== 'brokerage');
		return (list[0] ?? accounts[0])?.id ?? null;
	}

	function switchMode(m: typeof mode) {
		mode = m;
		reset();
		accountId = pick(m);
	}

	function reset() {
		fileName = '';
		content = '';
		inspection = null;
		mapping = null;
		preview = null;
		result = null;
		previewError = '';
	}

	async function choose(event: Event) {
		const file = (event.target as HTMLInputElement).files?.[0];
		if (!file) return;
		reset();
		fileName = file.name;
		content = await readFileText(file);
		if (mode === 'bank') {
			try {
				inspection = await rpc<ImportInspection>('import_inspect', { content });
				mapping = inspection.mapping;
			} catch (err) {
				toasts.error(err);
			}
		}
	}

	// Re-run the preview whenever the mapping or the account changes.
	$effect(() => {
		// Read every dependency up front so the effect re-runs on any of them.
		const current = mapping ? $state.snapshot(mapping) : null;
		const account = accountId;
		const text = content;
		if (mode !== 'bank' || !current || !account || !text) return;
		const args = { account_id: account, content: text, mapping: current };
		const timer = setTimeout(() => {
			rpc<ImportPreview>('import_preview', args)
				.then((p) => {
					preview = p;
					previewError = '';
				})
				.catch((err) => {
					preview = null;
					previewError = err.message;
				});
		}, 200);
		return () => clearTimeout(timer);
	});

	async function commitBank() {
		busy = true;
		try {
			const r = await rpc<{ imported: number; duplicates: number; errors: number }>('import_commit', { account_id: accountId, content, mapping });
			result = `Imported ${r.imported} transactions${r.duplicates ? `, skipped ${r.duplicates} already imported` : ''}${r.errors ? `, ${r.errors} unreadable ${r.errors === 1 ? 'row' : 'rows'} left out` : ''}.`;
			session.changed();
		} catch (err) {
			toasts.error(err);
		} finally {
			busy = false;
		}
	}

	async function commitTrades() {
		busy = true;
		try {
			const r = await rpc<{ imported: number; duplicates: number; created_assets: number; problems: string[] }>('import_trades', { account_id: accountId, content });
			result =
				`Imported ${r.imported} trades` +
				(r.duplicates ? `, skipped ${r.duplicates} already imported` : '') +
				(r.created_assets ? `, created ${r.created_assets} new assets (set their type, region and price source in Investments → Assets)` : '') +
				'.' +
				(r.problems.length ? ` ${r.problems.join('; ')}.` : '');
			session.changed();
		} catch (err) {
			toasts.error(err);
		} finally {
			busy = false;
		}
	}

	function seeImported() {
		resetTxFilters({ account_id: String(accountId) });
		goto(mode === 'trades' ? '#/investments' : '#/transactions');
	}

</script>

<div class="page">
	<header class="page-head">
		<div>
			<h1>Import</h1>
			<p>Read a CSV exported from your bank or broker. The file is read here and never leaves this device.</p>
		</div>
		<div class="tabs">
			<button class:active={mode === 'bank'} onclick={() => switchMode('bank')}>Bank statement</button>
			<button class:active={mode === 'trades'} onclick={() => switchMode('trades')}>Broker trades</button>
		</div>
	</header>

	{#if !accounts.length}
		<div class="card empty"><strong>Add an account first</strong><a href="#/accounts">Go to Accounts</a></div>
	{:else}
		<section class="card step">
			<div class="row">
				<label class="field">
					<span>Into account</span>
					<select class="input" bind:value={accountId}>
						{#each accounts as a (a.id)}<option value={a.id}>{a.name}</option>{/each}
					</select>
				</label>
				<label class="field">
					<span>CSV file</span>
					{#key fileName === ''}
						<input class="input file" type="file" accept=".csv,.txt,text/csv" onchange={choose} />
					{/key}
				</label>
			</div>
			{#if mode === 'trades'}
				<p class="faint">
					Expected columns, in this order: <code>date,symbol,side,quantity,price,fees</code>. Dates as YYYY-MM-DD, side as buy or sell.
					Rows already imported are skipped, and a sale of more units than you hold stops the import.
				</p>
			{/if}
		</section>

		{#if result}
			<section class="card done">
				<Icon name="shield" size={22} />
				<p>{result}</p>
				<div class="actions">
					<button class="btn" onclick={reset}>Import another file</button>
					<button class="btn primary" onclick={seeImported}>See them</button>
				</div>
			</section>
		{:else if mode === 'trades' && content}
			<section class="card step">
				<p>Ready to import <b>{fileName}</b>.</p>
				<div class="actions end"><button class="btn primary" disabled={busy} onclick={commitTrades}>Import trades</button></div>
			</section>
		{:else if mode === 'bank' && inspection && mapping}
			<section class="card step">
				<div class="card-head"><h2>Columns</h2><span class="faint">{inspection.rows} rows in {fileName}</span></div>
				<div class="mapping">
					<label class="field"><span>Date column</span>
						<select class="input" bind:value={mapping.date_column}>
							<option value={null}>Choose…</option>
							{#each inspection.headers as h, i (i)}<option value={i}>{h}</option>{/each}
						</select>
					</label>
					<label class="field"><span>Date format</span>
						<select class="input" bind:value={mapping.date_format}>
							<option value={null}>Choose…</option>
							{#each inspection.date_formats as f (f)}<option value={f}>{f.replace('%Y', 'YYYY').replace('%y', 'YY').replace('%m', 'MM').replace('%d', 'DD')}</option>{/each}
						</select>
					</label>
					<label class="field"><span>Description column</span>
						<select class="input" bind:value={mapping.payee_column}>
							<option value={null}>Choose…</option>
							{#each inspection.headers as h, i (i)}<option value={i}>{h}</option>{/each}
						</select>
					</label>
					<label class="field"><span>Amounts</span>
						<select class="input" bind:value={mapping.amount_mode}>
							<option value="single">One column, negative for money out</option>
							<option value="split">Separate in and out columns</option>
						</select>
					</label>
					{#if mapping.amount_mode === 'single'}
						<label class="field"><span>Amount column</span>
							<select class="input" bind:value={mapping.amount_column}>
								<option value={null}>Choose…</option>
								{#each inspection.headers as h, i (i)}<option value={i}>{h}</option>{/each}
							</select>
						</label>
					{:else}
						<label class="field"><span>Money out column</span>
							<select class="input" bind:value={mapping.debit_column}>
								<option value={null}>Choose…</option>
								{#each inspection.headers as h, i (i)}<option value={i}>{h}</option>{/each}
							</select>
						</label>
						<label class="field"><span>Money in column</span>
							<select class="input" bind:value={mapping.credit_column}>
								<option value={null}>Choose…</option>
								{#each inspection.headers as h, i (i)}<option value={i}>{h}</option>{/each}
							</select>
						</label>
					{/if}
					<label class="field"><span>Decimal separator</span>
						<select class="input" bind:value={mapping.decimal}>
							<option value="auto">Detect</option>
							<option value="comma">Comma (1.234,56)</option>
							<option value="dot">Dot (1,234.56)</option>
						</select>
					</label>
				</div>
				<div class="opts">
					<label class="check"><input type="checkbox" bind:checked={mapping.has_header} /> First row is a header</label>
					<label class="check"><input type="checkbox" bind:checked={mapping.invert} /> Flip signs (some card statements show spending as positive)</label>
				</div>
			</section>

			<section class="card step">
				<div class="card-head">
					<h2>Preview</h2>
					{#if preview}
						<span class="muted"><b class="pos">{preview.new} new</b> · {preview.duplicate} already imported · {preview.error} unreadable</span>
					{/if}
				</div>
				{#if previewError}
					<p class="error-text">{previewError}</p>
				{:else if preview}
					<div class="scroll">
						<table class="table">
							<thead><tr><th>Line</th><th>Date</th><th>Description</th><th>Category from rules</th><th class="right">Amount</th><th></th></tr></thead>
							<tbody>
								{#each preview.rows.slice(0, 60) as row (row.line)}
									<tr class:dim={row.status !== 'new'}>
										<td class="faint num">{row.line}</td>
										<td class="num">{row.date ? shortDate(row.date) : '—'}</td>
										<td>{row.payee}</td>
										<td class="muted">{row.category ?? ''}</td>
										<td class="right num" class:pos={(row.amount ?? 0) > 0}>{row.amount !== null ? money(row.amount, { sign: true }) : '—'}</td>
										<td>
											{#if row.status === 'duplicate'}<span class="pill">already imported</span>
											{:else if row.status === 'error'}<span class="pill err">{row.error}</span>{/if}
										</td>
									</tr>
								{/each}
							</tbody>
						</table>
					</div>
					<div class="actions end">
						<button class="btn primary" disabled={busy || !preview.new} onclick={commitBank}>
							Import {preview.new} transactions
						</button>
					</div>
				{/if}
			</section>
		{/if}
	{/if}
</div>

<style>
	.step {
		margin-bottom: 16px;
		display: grid;
		gap: 14px;
	}

	.step p {
		font-size: 13px;
	}

	.file {
		padding-top: 6px;
	}

	.mapping {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
		gap: 14px;
	}

	.opts {
		display: flex;
		gap: 24px;
		flex-wrap: wrap;
	}

	.scroll {
		max-height: 420px;
		overflow: auto;
	}

	tr.dim td {
		opacity: 0.5;
	}

	.pill.err {
		background: var(--neg-soft);
		color: var(--neg);
	}

	.end {
		justify-content: flex-end;
	}

	.done {
		display: flex;
		align-items: center;
		gap: 14px;
		margin-bottom: 16px;
	}

	.done :global(svg) {
		color: var(--pos);
		flex: none;
	}

	.done p {
		flex: 1;
	}
</style>
