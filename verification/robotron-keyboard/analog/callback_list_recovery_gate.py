"""Require complete bounded callback-list evidence before recovering typed-signal campaign."""
import math
FAULTS={'callback-list-'+field+'-corrupt' for field in ('user','object','function','link')}


def require(prior):
    if any(prior.get(k) is not True for k in ('controlsPassed','reviewCompleted','firmwareRecordsExactlyEqual')):raise ValueError('Need complete callback-list review, not startup or partial evidence')
    comparisons=prior.get('comparisons',{})
    if set(comparisons)!={'disabledBaseline','enabledObserver'}:raise ValueError('Missing normal comparisons')
    for result in comparisons.values():
        if result.get('allSamplesExactlyEqual') is not True or type(result.get('samples')) is not int or result['samples']<=0 or result.get('endSeconds')!=20e-6 or len(result.get('signals',[]))!=31 or len(set(result['signals']))!=31:raise ValueError('Incomplete exact waveform comparison')
    if comparisons['disabledBaseline']['signals']!=comparisons['enabledObserver']['signals'] or comparisons['disabledBaseline']['samples']!=comparisons['enabledObserver']['samples']:raise ValueError('Unmatched normal comparisons')
    state=prior.get('observedState',{});n=state.get('boundaries')
    if type(n) is not int or n<=0 or n%2 or state.get('wireObservations')!=n or state.get('wireKinds')!=[4,8] or state.get('maximumWireFilters',0)<=0 or state.get('signalObservations')!=n or state.get('maximumSignalFunctors',0)<=0 or state.get('muxObservations')!=n or state.get('maximumMuxFunctors',0)<=0 or state.get('gateObservations')!=n or state.get('maximumGateFunctors',0)<=0 or state.get('arithmeticObservations')!=n or state.get('maximumArithmeticFunctors',0)<=0 or state.get('reductionObservations')!=n or state.get('maximumReductionFunctors',0)<=0 or state.get('rawWireObservations')!=n or state.get('maximumRawWireFilters',0)<=0 or state.get('concatObservations')!=n or state.get('maximumConcatFunctors',0)<=0 or state.get('resolverObservations')!=n or state.get('maximumResolverFunctors',0)<=0 or state.get('rawIslandObservations')!=n or state.get('rawIslandCount',0)<=0 or state.get('maximumRawIslandCacheBytes',0)<=0 or state.get('rawAssignmentObservations')!=n or state.get('pendingRawAssignments',0)<=0 or state.get('uniqueRawAssignmentLifetimes',0)<=0 or state.get('maximumRawAssignmentBytes',0)<=0 or state.get('callbackListObservations')!=n or state.get('boundOutputCallbacks',0)<=0 or state.get('uniqueCallbackOwners',0)<=0 or state.get('maximumCallbackOwners',0)<=0:raise ValueError('Incomplete callback-list population/observations')
    if n!=2*comparisons['enabledObserver']['samples']:raise ValueError('Missing sample boundary observations')
    faults=prior.get('negativeControls',{})
    if set(faults)!=FAULTS:raise ValueError('Missing callback-list fault family')
    for name,result in faults.items():
        f=result.get('fault',{});index=f.get('index');tick=f.get('targetSeconds')
        if type(index) is not int or index<0 or type(tick) not in (int,float) or not math.isfinite(tick) or f.get('phase') not in ('before-step','after-step'):raise ValueError('Missing fault boundary')
        if index!=0 or tick!=0 or f['phase']!='before-step':raise ValueError('Callback-list fault missed startup')
    budgets=prior.get('captureLogBudgets',{})
    if set(budgets)!=FAULTS|{'off','observe'}:raise ValueError('Missing bounded callback-list receipts')
    for b in budgets.values():
        if b.get('logicalLimitBytes')!=56*1024**3 or b.get('compressedLimitBytes')!=256*1024**2:raise ValueError('Changed predecessor budget')
        if any(type(b.get(k)) is not int or not 0<b[k]<=cap for k,cap in (('bytes',56*1024**3),('compressedBytes',256*1024**2))):raise ValueError('Exceeded predecessor budget')
