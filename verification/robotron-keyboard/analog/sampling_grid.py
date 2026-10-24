"""Opt-in solver breakpoints for controlled absolute-time sampling experiments."""
import math


def add_sampling_grid(deck, times, stop_ns):
    if not isinstance(times,list) or not times or len(times)>10000:
        raise ValueError('Expected a bounded nonempty sampling grid')
    if stop_ns is None or not math.isfinite(stop_ns) or stop_ns<=0:
        raise ValueError('Sampling grid requires a finite positive stop time')
    if any(type(t) not in (int,float) or not math.isfinite(t) or t<=0 for t in times):
        raise ValueError('Sampling times must be finite and positive')
    if times!=sorted(set(times)):
        raise ValueError('Sampling times must be sorted and unique')
    if 'Vsampling_grid' in deck or deck.count('Vfixture_clock ')!=1:
        raise ValueError('Unexpected sampling-grid fixture')
    # Keep future points so bounded prefix controls retain the same fixture.
    grid='Vsampling_grid sampling_grid 0 PWL(0 0\n'+'\n'.join(f'+ {t:.17g} 0' for t in times)+'\n+ )\n'
    return deck.replace('Vfixture_clock ',grid+'Vfixture_clock ',1)
