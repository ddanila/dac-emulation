"""Require complete bounded signal evidence before recovering the mux campaign."""
import math
FAULTS={'signal-'+field+'-corrupt' for field in ('init','value','active')}


def require(prior):
    if any(prior.get(k) is not True for k in ('controlsPassed','reviewCompleted','firmwareRecordsExactlyEqual')):raise ValueError('Need complete signal review, not startup or partial evidence')
    comparisons=prior.get('comparisons',{})
    if set(comparisons)!={'disabledBaseline','enabledObserver'}:raise ValueError('Missing normal comparisons')
    for result in comparisons.values():
        if result.get('allSamplesExactlyEqual') is not True or type(result.get('samples')) is not int or result['samples']<=0 or result.get('endSeconds')!=20e-6 or len(result.get('signals',[]))!=31 or len(set(result['signals']))!=31:raise ValueError('Incomplete exact waveform comparison')
    if comparisons['disabledBaseline']['signals']!=comparisons['enabledObserver']['signals'] or comparisons['disabledBaseline']['samples']!=comparisons['enabledObserver']['samples']:raise ValueError('Unmatched normal comparisons')
    state=prior.get('observedState',{});n=state.get('boundaries')
    if type(n) is not int or n<=0 or n%2 or state.get('wireObservations')!=n or state.get('wireKinds')!=[4,8] or state.get('maximumWireFilters',0)<=0 or state.get('signalObservations')!=n or state.get('maximumSignalFunctors',0)<=0:raise ValueError('Incomplete signal population/observations')
    if n!=2*comparisons['enabledObserver']['samples']:raise ValueError('Missing sample boundary observations')
    faults=prior.get('negativeControls',{})
    if set(faults)!=FAULTS:raise ValueError('Missing signal fault family')
    for name,result in faults.items():
        f=result.get('fault',{});index=f.get('index');tick=f.get('targetSeconds')
        if type(index) is not int or index<0 or type(tick) not in (int,float) or not math.isfinite(tick) or f.get('phase') not in ('before-step','after-step'):raise ValueError('Missing fault boundary')
        if '-init-' in name:
            if index!=0 or tick!=0:raise ValueError('Initialization fault missed startup')
        elif index<=0 or tick<5e-6:raise ValueError('Later signal fault not exercised')
    budgets=prior.get('captureLogBudgets',{})
    if set(budgets)!=FAULTS|{'off','observe'}:raise ValueError('Missing bounded signal receipts')
    for b in budgets.values():
        if b.get('logicalLimitBytes')!=16*1024**3 or b.get('compressedLimitBytes')!=256*1024**2:raise ValueError('Changed predecessor budget')
        if any(type(b.get(k)) is not int or not 0<b[k]<=cap for k,cap in (('bytes',16*1024**3),('compressedBytes',256*1024**2))):raise ValueError('Exceeded predecessor budget')
