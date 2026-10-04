<script lang="ts">
	import { untrack } from 'svelte';
	import { rpc } from '#lib/api.ts';
	import { confirmAction } from '#lib/confirm.svelte.ts';
	import { ASSET_KINDS, price as formatPrice, REGIONS, shortDate, today } from '#lib/format.ts';
	import { session } from '#lib/session.svelte.ts';
	import { toasts } from '#lib/toast.svelte.ts';
	import type { Asset } from '#lib/types.ts';
	import Modal from '../Modal.svelte';

	let { asset, onclose }: { asset: Asset | null; onclose: () => void } = $props();

	let form = $state(
		untrack(() => ({
			id: asset?.id,
			symbol: asset?.symbol ?? '',
			name: asset?.name ?? '',
			kind: asset?.kind ?? 'etf',
			region: asset?.region ?? 'global',
			price_source: asset?.price_source ?? 'manual',
			source_id: asset?.source_id ?? ''
		}))
	);
	let manualPrice = $state<string>('');
	let priceDate = $state(today());
	let history = $state<{ date: string; price: number; source: string }[]>([]);
	let busy = $state(false);

	$effect(() => {
		if (asset) rpc<typeof history>('list_prices', { asset_id: asset.id }).then((h) => (history = h.slice(0, 6)));
	});

	async function save(event: SubmitEvent) {
		event.preventDefault();
		busy = true;
		try {
			const saved = await rpc<Asset>('save_asset', { asset: form });
			const value = Number(manualPrice.replace(',', '.'));
			if (manualPrice.trim() && Number.isFinite(value)) {
				await rpc('set_price', { price: { asset_id: saved.id, date: priceDate, price: value } });
			}
			toasts.show(form.id ? 'Asset updated' : 'Asset added');
			session.changed();
			onclose();
		} catch (err) {
			toasts.error(err);
		} finally {
			busy = false;
		}
	}

	async function remove() {
		if (!(await confirmAction({ title: `Delete ${form.symbol}?`, message: 'Its price history is deleted too.', confirm: 'Delete', danger: true }))) return;
		try {
			await rpc('delete_asset', { id: form.id });
			session.changed();
			onclose();
		} catch (err) {
			toasts.error(err);
		}
	}
</script>

<Modal title={form.id ? `Edit ${asset?.symbol}` : 'New asset'} {onclose} width={560}>
	<form id="asset-form" class="grid" onsubmit={save}>
		<div class="row">
			<label class="field"><span>Symbol</span><input class="input" bind:value={form.symbol} placeholder="GEQ" required /></label>
			<label class="field"><span>Type</span>
				<select class="input" bind:value={form.kind}>
					{#each Object.entries(ASSET_KINDS) as [value, label] (value)}<option {value}>{label}</option>{/each}
				</select>
			</label>
		</div>
		<label class="field"><span>Name</span><input class="input" bind:value={form.name} placeholder="Global Equity Index ETF" required /></label>
		<label class="field"><span>Region</span>
			<select class="input" bind:value={form.region}>
				{#each Object.entries(REGIONS) as [value, label] (value)}<option {value}>{label}</option>{/each}
			</select>
		</label>

		<fieldset>
			<legend>Prices</legend>
			<div class="row">
				<label class="field"><span>Source</span>
					<select class="input" bind:value={form.price_source}>
						<option value="manual">Typed by hand</option>
						<option value="yahoo">Yahoo Finance (ETFs, stocks)</option>
						<option value="coingecko">CoinGecko (crypto)</option>
					</select>
				</label>
				{#if form.price_source !== 'manual'}
					<label class="field">
						<span>{form.price_source === 'coingecko' ? 'Coin id' : 'Ticker on Yahoo'}</span>
						<input class="input" bind:value={form.source_id} placeholder={form.price_source === 'coingecko' ? 'bitcoin' : 'VWCE.DE'} />
					</label>
				{/if}
			</div>
			{#if form.price_source !== 'manual'}
				<small class="faint">Only this ticker is sent when refreshing prices. Pick a listing quoted in {session.currency}.</small>
			{/if}
			<div class="row">
				<label class="field"><span>Price</span><input class="input money" inputmode="decimal" bind:value={manualPrice} placeholder={asset?.last_price ? String(asset.last_price) : '0.00'} /></label>
				<label class="field"><span>On</span><input class="input" type="date" bind:value={priceDate} /></label>
			</div>
			{#if history.length}
				<ul class="history">
					{#each history as h (h.date)}
						<li><span class="muted">{shortDate(h.date)}</span><span class="num">{formatPrice(h.price)}</span><span class="faint">{h.source}</span></li>
					{/each}
				</ul>
			{/if}
		</fieldset>
	</form>
	{#snippet footer()}
		{#if form.id && !asset?.trades}<button class="btn danger" type="button" onclick={remove}>Delete</button><span style="flex:1"></span>{/if}
		<button class="btn" type="button" onclick={onclose}>Cancel</button>
		<button class="btn primary" form="asset-form" disabled={busy || !form.symbol.trim() || !form.name.trim()}>Save</button>
	{/snippet}
</Modal>

<style>
	fieldset {
		border: 1px solid var(--line);
		border-radius: var(--radius);
		padding: 12px 14px 14px;
		display: grid;
		gap: 12px;
		margin: 0;
	}

	legend {
		padding: 0 6px;
		color: var(--muted);
		font-size: 12px;
	}

	.history {
		list-style: none;
		margin: 0;
		padding: 0;
		font-size: 13px;
	}

	.history li {
		display: grid;
		grid-template-columns: 1fr 1fr 60px;
		padding: 3px 0;
	}
</style>
