<script lang="ts" module>
	import { BarChart, LineChart, PieChart } from 'echarts/charts';
	import { GridComponent, LegendComponent, MarkLineComponent, TooltipComponent } from 'echarts/components';
	import * as echarts from 'echarts/core';
	import { CanvasRenderer } from 'echarts/renderers';

	echarts.use([LineChart, BarChart, PieChart, GridComponent, TooltipComponent, LegendComponent, MarkLineComponent, CanvasRenderer]);

	export type ChartOption = echarts.EChartsCoreOption;
	export type ThemeColors = ReturnType<typeof themeColors>;

	/** Theme colours read from the CSS variables, so charts follow light and dark mode. */
	export function themeColors() {
		const style = getComputedStyle(document.documentElement);
		const get = (name: string) => style.getPropertyValue(name).trim();
		return {
			text: get('--text'),
			muted: get('--muted'),
			faint: get('--faint'),
			line: get('--line'),
			surface: get('--surface'),
			surface3: get('--surface-3'),
			accent: get('--accent'),
			pos: get('--pos'),
			neg: get('--neg'),
			font: get('--font')
		};
	}

	export function tooltipBase() {
		const c = themeColors();
		return {
			backgroundColor: c.surface,
			borderColor: c.line,
			borderWidth: 1,
			padding: [8, 11],
			textStyle: { color: c.text, fontSize: 12, fontFamily: c.font },
			extraCssText: 'box-shadow: 0 8px 24px rgba(0,0,0,.25); border-radius: 8px;'
		};
	}
</script>

<script lang="ts">
	interface Props {
		option: (colors: ThemeColors) => ChartOption;
		height?: number;
	}

	let { option, height = 260 }: Props = $props();
	let element: HTMLDivElement;
	let chart: echarts.ECharts | null = null;
	let scheme = $state(0);

	$effect(() => {
		chart = echarts.init(element, null, { renderer: 'canvas' });
		const resize = new ResizeObserver(() => chart?.resize());
		resize.observe(element);
		const media = window.matchMedia('(prefers-color-scheme: dark)');
		const onScheme = () => (scheme += 1);
		media.addEventListener('change', onScheme);
		return () => {
			resize.disconnect();
			media.removeEventListener('change', onScheme);
			chart?.dispose();
			chart = null;
		};
	});

	$effect(() => {
		void scheme;
		const colors = themeColors();
		chart?.setOption({ textStyle: { fontFamily: colors.font }, animationDuration: 500, ...option(colors) }, true);
	});
</script>

<div bind:this={element} style:height="{height}px" class="chart"></div>

<style>
	.chart {
		width: 100%;
		min-width: 0;
	}
</style>
