<script lang="ts">
	import { untrack } from 'svelte';
	import { currencySymbol, moneyInput, parseMoney } from '#lib/format.ts';

	interface Props {
		value: number | null;
		placeholder?: string;
		allowNegative?: boolean;
		id?: string;
	}

	let { value = $bindable(), placeholder = '0.00', allowNegative = false, id }: Props = $props();
	let text = $state(moneyInput(value));
	let invalid = $state(false);

	// Follow outside changes without fighting the user while they type.
	$effect(() => {
		const current = value;
		untrack(() => {
			if (!invalid && parseMoney(text) !== current) text = moneyInput(current);
		});
	});

	function input(event: Event) {
		text = (event.target as HTMLInputElement).value;
		const parsed = parseMoney(text);
		invalid = text.trim() !== '' && (parsed === null || (!allowNegative && parsed < 0));
		value = invalid ? null : parsed;
	}
</script>

<div class="money-input" class:invalid>
	<span>{currencySymbol()}</span>
	<input {id} class="input money" inputmode="decimal" {placeholder} value={text} oninput={input} autocomplete="off" />
</div>

<style>
	.money-input {
		position: relative;
	}

	span {
		position: absolute;
		left: 11px;
		top: 50%;
		transform: translateY(-50%);
		color: var(--faint);
		pointer-events: none;
		font-size: 13px;
	}

	input {
		padding-left: 28px;
	}

	.invalid input {
		border-color: var(--neg);
	}
</style>
