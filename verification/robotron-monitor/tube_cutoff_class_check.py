"""Check the CRT grid cut-off proxy against class and manual operating points.

The Tungsram M31-120 is a same-size comparator, not the installed B31G22.
The isolated neck's G1/G2 rails are provisional; the active tube omits G4.
"""
import argparse
import hashlib
import json
from pathlib import Path

import electrothermal


ROOT = Path(__file__).resolve().parent
TUNGSRAM_SHA256 = '3358775dc8165afc7036235d2887264820017453e13d3d0dd8dd52a40583ac15'
MANUAL_SHA256 = '7506b2fcf81bcc31ba3f6d27832b5295324bdd6cd91c459f3e7adb3701a67f21'
CATALOG_G2_V = 250.
CATALOG_GRID_CUTOFF_V = (35., 69.)
NECK_G1_V = -25.
NECK_G2_V = 350.
MANUAL_DARK_CATHODE_V = 35.
MANUAL_BRIGHT_CATHODE_V = 15.


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def drive_v(mu, cathode_v, g1_v=NECK_G1_V, g2_v=NECK_G2_V):
    """Active model's effective drive before the perveance exponent."""
    return g1_v-cathode_v+(g2_v-cathode_v)/mu


def cutoff_cathode_v(mu):
    return (NECK_G2_V+mu*NECK_G1_V)/(mu+1)


def run(tungsram_pdf, manual_pdf):
    if sha(tungsram_pdf) != TUNGSRAM_SHA256:
        raise ValueError('Tungsram catalog differs from inspected source')
    if sha(manual_pdf) != MANUAL_SHA256:
        raise ValueError('Robotron manual differs from inspected source')
    p = electrothermal.parameters()
    mu = p['grid2_mu']
    model = electrothermal.model()
    expression = (f'{p["perveance"]}*max(v(g1,cathode)+'
                  f'v(g2,cathode)/{mu},0)^1.5')
    if expression not in model:
        raise ValueError('active CRT cut-off law changed')
    # At cathode=0, cut-off is |G1|=G2/mu. At fixed G1/G2 rails,
    # dark must have zero drive and normal bright must have positive drive.
    comparator_mu = [CATALOG_G2_V/CATALOG_GRID_CUTOFF_V[1],
                     CATALOG_G2_V/CATALOG_GRID_CUTOFF_V[0]]
    dark_limit = (NECK_G2_V-MANUAL_DARK_CATHODE_V)/(
        MANUAL_DARK_CATHODE_V-NECK_G1_V)
    bright_limit = (NECK_G2_V-MANUAL_BRIGHT_CATHODE_V)/(
        MANUAL_BRIGHT_CATHODE_V-NECK_G1_V)
    overlap = [max(comparator_mu[0], dark_limit),
               min(comparator_mu[1], bright_limit)]
    if not overlap[0] < mu < overlap[1]:
        raise ValueError('nominal CRT proxy misses class/manual cut-off overlap')
    return dict(
        format='dac-monitor-tube-cutoff-class-check-v1',
        qualification='conditional class comparator and isolated neck rails only; no B31G22 gun or G4 qualification',
        sources=dict(
            tungsram=dict(url='https://frank.pocnet.net/other/Tungsram/Tungsram_ElectronTubes_Semiconductors_1976.pdf',
                          pdf_sha256=TUNGSRAM_SHA256, pdf_page=96, printed_page='II-46',
                          type='M31-120', exact_installed_type=False),
            robotron_manual=dict(file='older-operation.pdf', pdf_sha256=MANUAL_SHA256,
                                 pdf_pages=[10, 11], printed_pages=[8, 9])),
        active_model=dict(file='electrothermal.py', sha256=sha(ROOT/'electrothermal.py'),
                          nominal_grid2_mu=mu, bounds=list(electrothermal.BOUNDS['grid2_mu'][1:3]),
                          law='perveance * max(G1-K + (G2-K)/mu, 0)^1.5',
                          g4_modeled=False),
        catalog=dict(g2_v=CATALOG_G2_V, grid_control_cutoff_v=list(CATALOG_GRID_CUTOFF_V),
                     implied_mu=comparator_mu,
                     interpretation='effective mu for the M31-120 at its printed G4=0..350 V operation, not a B31G22 bound'),
        manual_and_isolated_neck=dict(
            manual_cathode_v=dict(dark=MANUAL_DARK_CATHODE_V,
                                  normal_bright=MANUAL_BRIGHT_CATHODE_V),
            provisional_g1_v=NECK_G1_V, provisional_g2_v=NECK_G2_V,
            rail_source='page16-neck-static.json isolated ideal-rail bench',
            dark_requires_mu_at_least=dark_limit,
            bright_requires_mu_below=bright_limit,
            overlap_with_catalog_mu=overlap),
        comparison=dict(
            previous_nominal_mu=10.,
            previous_catalog_grid_cutoff_v=CATALOG_G2_V/10.,
            previous_manual_bright_drive_v=drive_v(10., MANUAL_BRIGHT_CATHODE_V),
            nominal_catalog_grid_cutoff_v=CATALOG_G2_V/mu,
            nominal_cathode_cutoff_v=cutoff_cathode_v(mu),
            nominal_dark_drive_v=drive_v(mu, MANUAL_DARK_CATHODE_V),
            nominal_bright_drive_v=drive_v(mu, MANUAL_BRIGHT_CATHODE_V),
            nominal_dark_demand_a=p['perveance']*max(
                drive_v(mu, MANUAL_DARK_CATHODE_V), 0)**1.5,
            nominal_bright_demand_a=p['perveance']*max(
                drive_v(mu, MANUAL_BRIGHT_CATHODE_V), 0)**1.5),
        remaining=['identify installed B31G22 electrode and G4 dependence',
                   'qualify connected G1/G2 rails and sustained bright/dark emission',
                   'bound perveance and emission against tube or service data'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tungsram-pdf', type=Path, required=True)
    parser.add_argument('--manual-pdf', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = run(args.tungsram_pdf, args.manual_pdf)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print('catalog cutoff, dark/bright drive:',
          report['comparison']['nominal_catalog_grid_cutoff_v'],
          report['comparison']['nominal_dark_drive_v'],
          report['comparison']['nominal_bright_drive_v'])
