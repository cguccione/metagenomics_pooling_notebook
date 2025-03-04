import re
import numpy as np
import pandas as pd
import string
import seaborn as sns
import matplotlib.pyplot as plt
import warnings


REVCOMP_SEQUENCERS = ['HiSeq4000', 'MiniSeq', 'NextSeq', 'HiSeq3000',
                      'iSeq', 'NovaSeq']
OTHER_SEQUENCERS = ['HiSeq2500', 'HiSeq1500', 'MiSeq']


def read_plate_map_csv(f, sep='\t'):
    """
    reads tab-delimited plate map into a Pandas dataframe

    Parameters
    ----------
    f: fp or open filehandle
        plate map file

    Returns
    -------
    plate_df: pandas DataFrame object
        DataFrame relating sample name, well location, and blank status

    Raises
    ------
    UserWarning
        If there are wells with no sample names associated with them.
    AssertionError
        If there are repeated sample names.
    """

    plate_df = pd.read_csv(f, sep=sep)
    plate_df['Well'] = plate_df['Row'] + plate_df['Col'].map(str)

    null_samples = plate_df.Sample.isnull()
    if null_samples.any():
        warnings.warn(('This plate map contains %d empty wells, these will be '
                      'ignored') % null_samples.sum())

        # slice to the non-null samples and reset the index so samples are
        # still indexed with a continuous list of integers
        plate_df = plate_df[~null_samples]
        plate_df.reset_index(inplace=True, drop=True)

    duplicated_samples = plate_df.Sample[plate_df.Sample.duplicated()]
    if len(duplicated_samples):
        raise ValueError('The following sample names are duplicated %s' %
                         ', '.join(sorted(duplicated_samples)))

    return plate_df


# method to read minipico output
def read_pico_csv(f, sep='\t', plate_reader='Synergy_HT',
                  conc_col_name='Sample DNA Concentration'):
    """
    reads tab-delimited pico quant

    Parameters
    ----------
    f: fp or open filehandle
        pico quant file
    sep: str
        sep char used in quant file
    plate_reader: str
        plate reader used to generate quant file ['Synergy_HT',
        'SpectraMax_i3x']
    conc_col_name: str
        name to use for concentration column output

    Returns
    -------
    pico_df: pandas DataFrame object
        DataFrame relating well location and DNA concentration
    """
    if plate_reader == 'Synergy_HT':
        encoding, skipfooter = None, 5
    elif plate_reader == 'SpectraMax_i3x':
        encoding, skipfooter = 'utf-16', 15
    else:
        raise ValueError("Invalid plate reader %s" % plate_reader)
    if not hasattr(f, 'read'):
        f = open(f, encoding=encoding)

    pico_df = pd.read_csv(f, sep=sep, skiprows=2,
                          skipfooter=skipfooter, engine='python')

    # synergy's concentration column is "Concentration", spectramax's is
    # [Concentration]. Rename will ignore any labels not in the dataframe so
    # only one of the two label updates should happen
    pico_df.rename(columns={'Concentration': conc_col_name,
                            '[Concentration]': conc_col_name,
                            'Wells': 'Well'}, inplace=True)

    pico_df = pico_df[['Well', conc_col_name]].copy()

    # coerce oddball concentrations to np.nan
    pico_df[conc_col_name] = \
        pd.to_numeric(pico_df[conc_col_name], errors='coerce')

    return pico_df


def calculate_norm_vol(dna_concs, ng=5, min_vol=2.5, max_vol=3500,
                       resolution=2.5):
    """
    Calculates nanoliters of each sample to add to achieve a normalized pool

    Parameters
    ----------
    dna_concs : numpy array of float
        The concentrations calculated via PicoGreen (ng/uL)
    ng : float
        The amount of DNA to pool (ng)
    max_vol : float
        The maximum volume to pool (nL)
    min_vol : float
        The minimum volume to pool (nL)

    Returns
    -------
    sample_vols : numpy array of float
        The volumes to pool (nL)
    """
    sample_vols = ng / np.nan_to_num(dna_concs) * 1000

    sample_vols = np.clip(sample_vols, min_vol, max_vol)

    sample_vols = np.round(sample_vols / resolution) * resolution

    return(sample_vols)


def format_dna_norm_picklist(dna_vols, water_vols, wells, dest_wells=None,
                             dna_concs=None, sample_names=None,
                             sample_plates=None, water_plate_name='Water',
                             dna_plate_type='384PP_AQ_BP2_HT',
                             water_plate_type='384PP_AQ_BP2_HT',
                             dest_plate_name='NormalizedDNA'):
    """
    Writes Echo-format pick list to achieve a normalized input DNA pool

    Parameters
    ----------
    dna_vols:  numpy array of float
        The volumes of dna to add
    water_vols:  numpy array of float
        The volumes of water to add
    wells: numpy array of str
        The well codes in the same orientation as the DNA concentrations
    dest_wells: numpy array of str
        The well codes, in the same orientation as `wells`,
        in which to place each sample if reformatting
    dna_concs:  numpy array of float
        The concentrations calculated via PicoGreen (ng/uL)
    sample_names: numpy array of str
        The sample names in the same orientation as the DNA concentrations
    sample_plates: numpy array of str
        The sample plates in the same orientation as the DNA concentrations

    Returns
    -------
    picklist : str
        The Echo formatted pick list
    """

    # check that arrays are the right size
    if dna_vols.shape != wells.shape != water_vols.shape:
        raise ValueError(('dna_vols %r has a size different from wells %r or '
                          'water_vols %r') %
                         (dna_vols.shape, wells.shape, water_vols.shape))

    # if destination wells not specified, use source wells
    if dest_wells is None:
        dest_wells = wells

    if sample_names is None:
        sample_names = np.empty(dna_vols.shape) * np.nan
    if sample_plates is None:
        sample_plates = 'Sample'
    if isinstance(sample_plates, str):
        sample_plates = np.full_like(dna_vols, sample_plates, dtype=object)
    if dna_plate_type is None:
        dna_plate_type = '384PP_AQ_BP2_HT'
    if isinstance(dna_plate_type, str):
        dna_plate_type = np.full_like(dna_vols, dna_plate_type, dtype=object)
    if dna_concs is None:
        dna_concs = np.empty(dna_vols.shape) * np.nan
    if (dna_concs.shape != sample_names.shape != dna_vols.shape
       != sample_plates.shape != dna_plate_type.shape):
        raise ValueError(('dna_vols %r has a size different from dna_concs %r'
                          ' or sample_names %r') %
                         (dna_vols.shape, dna_concs.shape, sample_names.shape))

    picklist = ''

    # header
    picklist += ('Sample\tSource Plate Name\tSource Plate Type\tSource Well\t'
                 'Concentration\tTransfer Volume\tDestination Plate Name\t'
                 'Destination Well')

    # water additions
    for index, sample in np.ndenumerate(sample_names):
        picklist += '\n' + '\t'.join([str(sample), water_plate_name,
                                      water_plate_type, str(wells[index]),
                                      str(dna_concs[index]),
                                      str(water_vols[index]),
                                      dest_plate_name, str(dest_wells[index])])
    # DNA additions
    for index, sample in np.ndenumerate(sample_names):
        picklist += '\n' + '\t'.join([str(sample), str(sample_plates[index]),
                                      str(dna_plate_type[index]),
                                      str(wells[index]), str(dna_concs[index]),
                                      str(dna_vols[index]),
                                      dest_plate_name, str(dest_wells[index])])

    return(picklist)


def assign_index(samples, index_df, start_idx=0):
    """
    Writes Echo-format pick list to achieve a normalized input DNA pool

    Parameters
    ----------
    samples:  int
        The number of samples for which to get indices
    index_df:  pandas DataFrame
        The dataframe of complete index combinations and information
    start_idx: int
        The starting index combo to use

    Returns
    -------
    indices : pandasDataFrame
        The index information for the chosen indices
    """

    indices = index_df.iloc[start_idx:(start_idx + samples)]

    return(indices)


def format_index_picklist(sample_names, sample_wells, indices,
                          i5_vol=250, i7_vol=250,
                          i5_plate_type='384LDV_AQ_B2_HT',
                          i7_plate_type='384LDV_AQ_B2_HT',
                          dest_plate_name='IndexPCRPlate'):
    """
    Writes Echo-format pick list to achieve a normalized input DNA pool

    Parameters
    ----------
    sample_names:  array-like of str
        The sample names matching index order of indices
    sample_wells:  array-like of str
        The wells matching sample name order
    indices: pandas DataFrame
        The dataframe with index info matching sample_names

    Returns
    -------
    picklist : str
        The Echo formatted pick list
    """

    # check that arrays are the right size
    if len(sample_names) != len(sample_wells) != len(indices):
        raise ValueError(('sample_names (%s) has a size different from '
                          'sample_wells (%s) or index list (%s)') %
                         (len(sample_names), len(sample_wells), len(indices)))

    picklist = ''

    # header
    picklist += ('Sample\tSource Plate Name\tSource Plate Type\tSource Well\t'
                 'Transfer Volume\tIndex Name\tIndex Sequence\tIndex Combo\t'
                 'Destination Plate Name\tDestination Well')

    # i5 additions
    for i, (sample, well) in enumerate(zip(sample_names, sample_wells)):
        picklist += '\n' + '\t'.join([str(sample), indices.iloc[i]['i5 plate'],
                                      i5_plate_type,
                                      indices.iloc[i]['i5 well'], str(
                                          i5_vol), indices.iloc[i]['i5 name'],
                                      indices.iloc[i]['i5 sequence'], str(
                                          indices.iloc[i]['index combo']),
                                      dest_plate_name, well])
    # i7 additions
    for i, (sample, well) in enumerate(zip(sample_names, sample_wells)):
        picklist += '\n' + '\t'.join([str(sample), indices.iloc[i]['i7 plate'],
                                      i7_plate_type,
                                      indices.iloc[i]['i7 well'], str(
                                          i7_vol), indices.iloc[i]['i7 name'],
                                      indices.iloc[i]['i7 sequence'], str(
                                          indices.iloc[i]['index combo']),
                                      dest_plate_name, well])

    return(picklist)


def compute_qpcr_concentration(cp_vals, m=-3.231, b=12.059, dil_factor=25000):
    """Computes molar concentration of libraries from qPCR Cp values.

    Returns a 2D array of calculated concentrations, in nanomolar units

    Parameters
    ----------
    cp_vals : numpy array of float
        The Cp values parsed from the plate reader
    m : float
        The slope of the qPCR standard curve
    b : float
        The intercept of the qPCR standard curve
    dil_factor: float or int
        The dilution factor of the samples going into the qPCR

    Returns
    -------10
    np.array of floats
        A 2D array of floats
    """
    qpcr_concentration = np.power(10, ((cp_vals - b) / m)) * dil_factor / 1000

    return(qpcr_concentration)


def compute_shotgun_pooling_values_eqvol(sample_concs, total_vol=60.0):
    """Computes molar concentration of libraries from qPCR Cp values.

    Returns a 2D array of calculated concentrations, in nanomolar units

    Parameters
    ----------
    sample_concs : numpy array of float
        The concentrations calculated via qPCR (nM)
    total_vol : float
        The total volume to pool (uL)

    Returns
    -------
    np.array of floats
        A 2D array of floats
    """
    per_sample_vol = (total_vol / sample_concs.size) * 1000.0

    sample_vols = np.zeros(sample_concs.shape) + per_sample_vol

    return(sample_vols)


def compute_shotgun_pooling_values_qpcr(sample_concs, sample_fracs=None,
                                        min_conc=10, floor_conc=50,
                                        total_nmol=.01):
    """Computes pooling volumes for samples based on qPCR estimates of
    nM concentrations (`sample_concs`).

    Reads in qPCR values in nM from output of `compute_qpcr_concentration`.
    Samples must be above a minimum concentration threshold (`min_conc`,
    default 10 nM) to be included. Samples above this threshold but below a
    given floor concentration (`floor_conc`, default 50 nM) will be pooled as
    if they were at the floor concentration, to avoid overdiluting the pool.

    Samples can be assigned a target molar fraction in the pool by passing a
    np.array (`sample_fracs`, same shape as `sample_concs`) with fractional
    values per sample. By default, will aim for equal molar pooling.

    Finally, total pooling size is determined by a target nanomolar quantity
    (`total_nmol`, default .01). For a perfect 384 sample library, in which you
    had all samples at a concentration of exactly 400 nM and wanted a total
    volume of 60 uL, this would be 0.024 nmol.

    Parameters
    ----------
    sample_concs: 2D array of float
        nM calculated by compute_qpcr_concentration
    sample_fracs: 2D of float
        fractional value for each sample (default 1/N)
    min_conc: float
        minimum nM concentration to be included in pool
    floor_conc: float
        minimum value for pooling for samples above min_conc
        corresponds to a maximum vol in pool
    total_nmol : float
        total number of nM to have in pool

    Returns
    -------
    sample_vols: np.array of floats
        the volumes in nL per each sample pooled
    """

    if sample_fracs is None:
        sample_fracs = np.ones(sample_concs.shape) / sample_concs.size

    # get samples above threshold
    sample_fracs_pass = sample_fracs.copy()
    sample_fracs_pass[sample_concs <= min_conc] = 0

    # renormalize to exclude lost samples
    sample_fracs_pass *= 1/sample_fracs_pass.sum()

    # floor concentration value
    sample_concs_floor = sample_concs.copy()
    sample_concs_floor[sample_concs < floor_conc] = floor_conc

    # calculate volumetric fractions including floor val
    sample_vols = (total_nmol * sample_fracs_pass) / sample_concs_floor

    # convert L to nL
    sample_vols *= 10**9

    return(sample_vols)


def compute_shotgun_pooling_values_qpcr_minvol(sample_concs, sample_fracs=None,
                                               floor_vol=100, floor_conc=40,
                                               total_nmol=.01):
    """Computes pooling volumes for samples based on qPCR estimates of
    nM concentrations (`sample_concs`), taking a minimum volume of samples
    below a threshold.

    Reads in qPCR values in nM from output of `compute_qpcr_concentration`.
    Samples below a minimum concentration (`floor_conc`, default 40 nM)
    will be included, but at a decreased volume (`floor_vol`, default 100 nL)
    to avoid overdiluting the pool.

    Samples can be assigned a target molar fraction in the pool by passing a
    np.array (`sample_fracs`, same shape as `sample_concs`) with fractional
    values per sample. By default, will aim for equal molar pooling.

    Finally, total pooling size is determined by a target nanomolar quantity
    (`total_nmol`, default .01). For a perfect 384 sample library, in which you
    had all samples at a concentration of exactly 400 nM and wanted a total
    volume of 60 uL, this would be 0.024 nmol.

    For a Novaseq, we expect to need 150 uL at 4 nM, or about 0.0006 nmol.
    Taking into account sample loss on the pippin prep (1/2) and molar loss
    due to exclusion of primer dimers (1/2), figure we need 4 times that or
    0.0024.

    Parameters
    ----------
    sample_concs: 2D array of float
        nM calculated by compute_qpcr_concentration
    sample_fracs: 2D of float
        fractional value for each sample (default 1/N)
    floor_vol: float
        volume (nL) at which samples below floor_conc will be pooled
    floor_conc: float
        minimum value (nM) for pooling at real estimated value (default 40)
    total_nmol : float
        total number of nM to have in pool

    Returns
    -------
    sample_vols: np.array of floats
        the volumes in nL per each sample pooled
    """

    if sample_fracs is None:
        sample_fracs = np.ones(sample_concs.shape) / sample_concs.size

    # calculate volumetric fractions including floor val
    sample_vols = (total_nmol * sample_fracs) / sample_concs

    # convert L to nL
    sample_vols *= 10**9

    # drop volumes for samples below floor concentration to floor_vol
    sample_vols[sample_concs < floor_conc] = floor_vol

    return(sample_vols)


def estimate_pool_conc_vol(sample_vols, sample_concs):
    """Estimates the actual molarity and volume of a pool.

    Parameters
    ----------
    sample_concs : numpy array of float
        The concentrations calculated via qPCR (nM)
    sample_vols : numpy array of float
        The calculated pooling volumes (nL)

    Returns
    -------
    pool_conc : float
        The estimated actual concentration of the pool, in nM
    total_vol : float
        The total volume of the pool, in nL
    """
    # scalar to adjust nL to L for molarity calculations
    nl_scalar = 10**-9

    # calc total pool pmols
    total_pmols = np.multiply(sample_concs, sample_vols) * nl_scalar

    # calc total pool vol in nanoliters
    total_vol = sample_vols.sum()

    # pool pM is total pmols divided by total liters
    # (total vol in nL * 1 L / 10^9 nL)
    pool_conc = total_pmols.sum() / (total_vol * nl_scalar)

    return(pool_conc, total_vol)


def format_pooling_echo_pick_list(vol_sample,
                                  max_vol_per_well=60000,
                                  dest_plate_shape=[16, 24]):
    """Format the contents of an echo pooling pick list

    Parameters
    ----------
    vol_sample : 2d numpy array of floats
        The per well sample volume, in nL
    max_vol_per_well : 2d numpy array of floats
        Maximum destination well volume, in nL
    """
    contents = ['Source Plate Name,Source Plate Type,Source Well,'
                'Concentration,Transfer Volume,Destination Plate Name,'
                'Destination Well']
    # Write the sample transfer volumes
    rows, cols = vol_sample.shape

    # replace NaN values with 0s to leave a trail of unpooled wells
    pool_vols = np.nan_to_num(vol_sample)

    running_tot = 0
    d = 1
    for i in range(rows):
        for j in range(cols):
            well_name = "%s%d" % (chr(ord('A') + i), j+1)
            # Machine will round, so just give it enough info to do the
            # correct rounding.
            val = "%.2f" % pool_vols[i][j]

            # test to see if we will exceed total vol per well
            if running_tot + pool_vols[i][j] > max_vol_per_well:
                d += 1
                running_tot = pool_vols[i][j]
            else:
                running_tot += pool_vols[i][j]

            dest = "%s%d" % (chr(ord('A') +
                                 int(np.floor(d/dest_plate_shape[0]))),
                             (d % dest_plate_shape[1]))

            contents.append(
                ",".join(['1', '384LDV_AQ_B2_HT', well_name, "",
                          val, 'NormalizedDNA', dest]))

    return "\n".join(contents)


def plot_plate_vals(dataset, color_map='YlGnBu', annot_str=None,
                    annot_fmt='.5s'):
    """
    Plots values in a plate format. Returns a heatmap in the shape of the
    plate, with bar graphs aligned to the rows and columns showing the mean and
    spread of each row and column, and a histogram showing the distribution of
    values.

    Optionally can plot an array of names or other annotations on top of the
    heatmap.

    Parameters
    ----------
    dataset: 2D array of numeric
        data to plot
    color_map: str
        matplotlib color map name for heatmap
    annot_str: 2D array of str
        values to write over heatmap values to annotate wells
    annot_fmt: str
        string formatting values for annotations. Defaults to first 5 char per
        well.

    Returns
    -------
    """
    plt.figure(figsize=(20, 20))

    with sns.axes_style("white"):
        ax1 = plt.subplot2grid((40, 20), (20, 0), colspan=18, rowspan=18)
        ax1.xaxis.tick_top()
        if annot_str is None:
            sns.heatmap(dataset,
                        ax=ax1,
                        xticklabels=[x + 1 for x in range(dataset.shape[1])],
                        yticklabels=list(string.ascii_uppercase)[
                            0:dataset.shape[0]],
                        # square = True,
                        annot=True,
                        fmt='.0f',
                        cmap=color_map,
                        cbar=False)
        else:
            sns.heatmap(dataset,
                        ax=ax1,
                        xticklabels=[x + 1 for x in range(dataset.shape[1])],
                        yticklabels=list(string.ascii_uppercase)[
                            0:dataset.shape[0]],
                        # square = True,
                        annot=annot_str,
                        fmt=annot_fmt,
                        cmap=color_map,
                        cbar=False)

    with sns.axes_style("white"):
        ax2 = plt.subplot2grid((40, 20), (38, 0), colspan=18, rowspan=2)
        ax3 = plt.subplot2grid((40, 20), (20, 18), colspan=2, rowspan=18)
        sns.despine()
        sns.barplot(data=dataset, orient='v', ax=ax2, color='grey')
        sns.barplot(data=dataset.transpose(), orient='h', ax=ax3,
                    color='grey')
        ax2.set(xticklabels=[], yticklabels=[])
        ax3.set(xticklabels=[], yticklabels=[])

    with sns.axes_style():
        ax4 = plt.subplot2grid((40, 20), (0, 0), colspan=18, rowspan=18)
        sns.distplot(dataset.flatten()[~np.isnan(dataset.flatten())], ax=ax4,
                     bins=20)

    return


def make_2D_array(qpcr, data_col='Cp', well_col='Pos', rows=16, cols=24):
    """
    Pulls a column of data out of a dataframe and puts into array format
    based on well IDs in another column

    Parameters
    ----------
    qpcr: Pandas DataFrame
        dataframe from which to pull values
    data_col: str
        name of column with data
    well_col: str
        name of column with well IDs, in 'A1,B12' format
    rows: int
        number of rows in array to return
    cols: int
        number of cols in array to return

    Returns
    -------
    """
    # initialize empty Cp array
    cp_array = np.empty((rows, cols), dtype=object)

    # fill Cp array with the post-cleaned values from the right half of the
    # plate
    for record in qpcr.iterrows():
        row = ord(str.upper(record[1][well_col][0])) - ord('A')
        col = int(record[1][well_col][1:]) - 1
        cp_array[row, col] = record[1][data_col]

    return(cp_array)


def combine_dfs(qpcr_df, dna_picklist, index_picklist):
    """
    Combines information from the three dataframes into a single frame suitable
    for plotting

    Parameters
    ----------
    qpcr_df: Pandas DataFrame
        df from qpcr data import. Expects cols ['Pos','Cp']
    dna_picklist: Pandas DataFrame
        df from DNA picklist import. Expects cols
        ['Destination Well', 'Concentration', 'Transfer Volume']
    index_picklist: Pandas DataFrame
        df from index addition picklist import. Expects cols
        ['Destination Well','Plate','Sample Name',
         'Counter','Primer','Source Well','Index']

    Returns
    -------
    combined_df: Pandas DataFrame
        new DataFrame with the relevant columns
    """
    combined_df = pd.DataFrame({'Well': qpcr_df['Pos'],
                                'Cp': qpcr_df['Cp']})

    combined_df.set_index('Well', inplace=True)

    b = dna_picklist.loc[dna_picklist['Source Plate Name'] != 'water',
                         ].set_index('Destination Well')
    c = index_picklist.loc[index_picklist['Source Plate Name'] ==
                           'i7 Source Plate', ].set_index('Destination Well')
    d = index_picklist.loc[index_picklist['Source Plate Name'] ==
                           'i5 Source Plate', ].set_index('Destination Well')

    # Add DNA conc columns
    combined_df['DNA Concentration'] = b['Concentration']
    combined_df['DNA Transfer Volume'] = b['Transfer Volume']

    # Add Index columns
    combined_df['Sample Name'] = c['Sample Name']
    combined_df['Plate'] = c['Plate']
    combined_df['Counter'] = d['Counter']
    combined_df['Source Well i7'] = c['Source Well']
    combined_df['Index i7'] = c['Index']
    combined_df['Primer i7'] = c['Primer']
    combined_df['Source Well i5'] = d['Source Well']
    combined_df['Index i5'] = d['Index']
    combined_df['Primer i5'] = d['Primer']

    combined_df.reset_index(inplace=True)

    return(combined_df)


def parse_dna_conc_csv(fp):
    dna_df = pd.read_excel(fp, skiprows=4, parse_cols=[1, 2, 3, 4, 5])

    dna_df = dna_df.loc[list(range(384)), ]

    dna_df['pico_conc'] = pd.to_numeric(
        dna_df['[Concentration]'], errors='Coerce')
    return(dna_df)


def add_dna_conc(combined_df, dna_df):
    new_df = combined_df.set_index('Well')

    new_df['pico_conc'] = dna_df.set_index('Well')['pico_conc']

    new_df.reset_index(inplace=True)

    return(new_df)


def compute_pico_concentration(dna_vals, size=400):
    """Computes molar concentration of libraries from library DNA concentration
    values.

    Returns a 2D array of calculated concentrations, in nanomolar units

    Parameters
    ----------
    dna_vals : numpy array of float
        The DNA concentration in ng/uL
    size : int
        The average library molecule size in bp

    Returns
    -------
    np.array of floats
        A 2D array of floats
    """
    lib_concentration = (dna_vals / (660 * float(size))) * 10**6

    return(lib_concentration)


def bcl_scrub_name(name):
    """Modifies a sample name to be BCL2fastq compatible

    Parameters
    ----------
    name : str
        the sample name

    Returns
    -------
    str
        the sample name, formatted for bcl2fastq
    """

    return re.sub(r'[^0-9a-zA-Z\-\_]+', '_', name)


def rc(seq):
    """
    from http://stackoverflow.com/a/25189185/7146785
    """
    complement = {'A': 'T', 'C': 'G', 'G': 'C', 'T': 'A'}

    rev_seq = "".join(complement.get(base, base) for base in reversed(seq))

    return(rev_seq)


def sequencer_i5_index(sequencer, indices):

    if sequencer in REVCOMP_SEQUENCERS:
        print('%s: i5 barcodes are output as reverse compliments' % sequencer)
        return([rc(x) for x in indices])
    elif sequencer in OTHER_SEQUENCERS:
        print('%s: i5 barcodes are output in standard direction' % sequencer)
        return(indices)
    else:
        raise ValueError(('Your indicated sequencer [%s] is not recognized.\n'
                          'Recognized sequencers are: \n %s') %
                         (sequencer,
                          ', '.join(REVCOMP_SEQUENCERS + OTHER_SEQUENCERS)))


def reformat_interleaved_to_columns(wells):
    """
    converts condensed 96-to-384 plates in this format:

    plate1 | plate2
    ---------------
    plate3 | plate4

    to this format:

    plate1 | plate2 | plate3 | plate4

    where samples for each of the constituent plates are packed into contiguous
    columns of the 384 well plate.

    This is useful when doing a 192 well plate in order to save Mosquito tips /
    time

    Parameters
    ----------
    wells: array-like of str
        the sample source wells

    Returns
    -------
    new_wells: np array of str
        then new well locations in matching array positions
    """

    wells = np.array(wells)
    new_wells = np.empty(np.shape(wells), dtype='object')

    for i, owell in np.ndenumerate(wells):
        row = ord(str(owell[0]).upper()) - 65
        col = int(owell[1:]) - 1

        # ROWS
        # roffset = ROW % 2
        # row = ROW - roffset + floor(COL / 12)

        roffset = row % 2
        nrow = int(row - roffset + np.floor(col / 12))

        # COLS
        # coffset = COL % 2 + (ROW % 2) * 2
        # col = coffset * 6 + (col / 2) % 6

        coffset = col % 2 + (row % 2) * 2
        ncol = int(coffset * 6 + (col / 2) % 6)

        nwell = '%s%s' % (chr(nrow + 65), ncol + 1)

        new_wells[i] = nwell

    return(new_wells)
