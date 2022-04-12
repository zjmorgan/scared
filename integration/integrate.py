# import mantid algorithms, numpy and matplotlib
from mantid.simpleapi import *
import matplotlib.pyplot as plt
import numpy as np

import sys, os, re, imp, copy

import itertools

directory = os.path.dirname(os.path.realpath(__file__))
sys.path.append(directory)

import multiprocessing

import merge, peak, parameters

imp.reload(merge)
imp.reload(peak)
imp.reload(parameters)

from peak import PeakDictionary
from PyPDF2 import PdfFileMerger

from mantid.kernel import V3D

filename, n_proc = sys.argv[1], int(sys.argv[2])

if n_proc > os.cpu_count():
    n_proc = os.cpu_count()

scale_constant = 1e+4

if __name__ == '__main__':
    multiprocessing.freeze_support()
    __spec__ = "ModuleSpec(name='builtins', loader=<class '_frozen_importlib.BuiltinImporter'>)"

    with multiprocessing.get_context('spawn').Pool(processes=n_proc) as pool:

        CreateSampleWorkspace(OutputWorkspace='sample')

        dictionary = parameters.load_input_file(filename)

        a = dictionary['a']
        b = dictionary['b']
        c = dictionary['c']
        alpha = dictionary['alpha']
        beta = dictionary['beta']
        gamma = dictionary['gamma']

        reflection_condition = dictionary['reflection-condition']
        group = dictionary['group']

        if reflection_condition == 'P':
            reflection_condition = 'Primitive'
        elif reflection_condition == 'F':
            reflection_condition = 'All-face centred'
        elif reflection_condition == 'I':
            reflection_condition = 'Body centred'
        elif reflection_condition == 'A':
            reflection_condition = 'A-face centred'
        elif reflection_condition == 'B':
            reflection_condition = 'B-face centred'
        elif reflection_condition == 'C':
            reflection_condition = 'C-face centred'
        elif reflection_condition == 'R' or reflection_condition == 'Robv':
            reflection_condition = 'Rhombohedrally centred, obverse'
        elif reflection_condition == 'Rrev':
            reflection_condition = 'Rhombohedrally centred, reverse'
        elif reflection_condition == 'H':
             reflection_condition = 'Hexagonally centred, reverse'
            
        if dictionary['chemical-formula'] is not None:
            chemical_formula = ''.join([' '+item if item.isalpha() else item for item in re.findall(r'[A-Za-z]+|\d+', dictionary['chemical-formula'])]).lstrip(' ')
        else:
            chemical_formula = dictionary['chemical-formula']

        z_parameter = dictionary['z-parameter']
        sample_mass = dictionary['sample-mass']

        facility, instrument = merge.set_instrument(dictionary['instrument'])
        ipts = dictionary['ipts']

        working_directory = '/{}/{}/IPTS-{}/shared/'.format(facility,instrument,ipts)
        shared_directory = '/{}/{}/shared/'.format(facility,instrument)

        run_nos = dictionary['runs'] if type(dictionary['runs']) is list else [dictionary['runs']]

        run_labels = '_'.join([str(r[0])+'-'+str(r[-1]) if type(r) is list else str(r) for r in run_nos if any([type(item) is list for item in run_nos])])

        if run_labels == '':
            run_labels = str(run_nos[0])+'-'+str(run_nos[-1])

        runs = []
        for r in run_nos:
            if type(r) is list:
                runs += r
            else:
                runs += [r]
                
        if n_proc > len(runs):
            n_proc = len(runs)

        experiment = dictionary['experiment']

        if dictionary['ub-file'] is not None:
            ub_file = os.path.join(working_directory, dictionary['ub-file'])

        split_angle = dictionary['split-angle']

        directory = os.path.dirname(os.path.abspath(filename))
        outname = dictionary['name']
        
        parameters.output_input_file(filename, directory, outname)

        if dictionary['flux-file'] is not None:
            spectrum_file = os.path.join(shared_directory+'Vanadium', dictionary['flux-file'])
        else:
            spectrum_file = None

        if dictionary['vanadium-file'] is not None:
            counts_file = os.path.join(shared_directory+'Vanadium', dictionary['vanadium-file'])
        else:
            counts_file = None

        if dictionary['tube-file'] is not None:
            tube_calibration = os.path.join(shared_directory+'calibration', dictionary['tube-file'])
        else:
            tube_calibration = None

        if dictionary['detector-file'] is not None:
            detector_calibration = os.path.join(shared_directory+'calibration', dictionary['detector-file'])
        else:
            detector_calibration = None

        mod_vector_1 = dictionary['modulation-vector-1']
        mod_vector_2 = dictionary['modulation-vector-2']
        mod_vector_3 = dictionary['modulation-vector-3']
        max_order = dictionary['max-order']
        cross_terms = dictionary['cross-terms']

        if not all([a,b,c,alpha,beta,gamma]):
            LoadIsawUB(InputWorkspace='sample', Filename=ub_file)
            a = mtd['sample'].sample().getOrientedLattice().a()
            b = mtd['sample'].sample().getOrientedLattice().b()
            c = mtd['sample'].sample().getOrientedLattice().c()
            alpha = mtd['sample'].sample().getOrientedLattice().alpha()
            beta = mtd['sample'].sample().getOrientedLattice().beta()
            gamma = mtd['sample'].sample().getOrientedLattice().gamma()

        ref_dict = dictionary.get('peak-dictionary')

        merge.load_normalization_calibration(facility, instrument, spectrum_file, counts_file,
                                             tube_calibration, detector_calibration)

        if facility == 'HFIR':
            ows = '{}_{}'.format(instrument,experiment)+'_{}'
        else:
            ows = '{}'.format(instrument)+'_{}'

        opk = ows+'_pk'
        omd = ows+'_md'

        for r in runs:
            if mtd.doesExist(omd.format(r)):
                DeleteWorkspace(omd.format(r))

        tmp = ows.format(run_labels)

        if os.path.exists(os.path.join(directory, tmp+'_pk.nxs')) and not mtd.doesExist(tmp):
            
            LoadNexus(Filename=os.path.join(directory, tmp+'_pk.nxs'), OutputWorkspace=tmp)
            LoadIsawUB(InputWorkspace=tmp, Filename=os.path.join(directory, tmp+'.mat'))

            for r in runs:
                FilterPeaks(InputWorkspace=tmp, 
                            FilterVariable='RunNumber',
                            FilterValue=r,
                            Operator='=',
                            OutputWorkspace=opk.format(r))
                            
        if not mtd.doesExist(tmp):

            split_runs = [split.tolist() for split in np.array_split(runs, n_proc)]

            args = [directory, facility, instrument, ipts, ub_file, reflection_condition,
                    spectrum_file, counts_file, tube_calibration, detector_calibration,
                    mod_vector_1, mod_vector_2, mod_vector_3, max_order, cross_terms, experiment]

            join_args = [(split, outname+'_p{}'.format(i), *args) for i, split in enumerate(split_runs)]

            pool.starmap(merge.pre_integration, join_args)

        if not mtd.doesExist(tmp):   
            
            if mtd.doesExist('sa'):
                CreatePeaksWorkspace(InstrumentWorkspace='sa', NumberOfPeaks=0, OutputType='Peak', OutputWorkspace=tmp)
            else:
                CreatePeaksWorkspace(InstrumentWorkspace='van', NumberOfPeaks=0, OutputType='Peak', OutputWorkspace=tmp)

            for i in range(n_proc):
                partname = outname+'_p{}'.format(i)

                LoadNexus(Filename=os.path.join(directory, partname+'_pk.nxs'), OutputWorkspace=partname+'_pk')
                LoadIsawUB(InputWorkspace=partname+'_pk', Filename=os.path.join(directory, partname+'.mat'))
                CombinePeaksWorkspaces(LHSWorkspace=partname+'_pk', RHSWorkspace=tmp, OutputWorkspace=tmp)
                LoadIsawUB(InputWorkspace=tmp, Filename=os.path.join(directory, partname+'.mat'))
                DeleteWorkspace(partname+'_pk')

                os.remove(os.path.join(directory, partname+'_pk.nxs'))
                os.remove(os.path.join(directory, partname+'.mat'))
 
            SaveNexus(InputWorkspace=tmp, Filename=os.path.join(directory, tmp+'_pk.nxs'))
            SaveIsawUB(InputWorkspace=tmp, Filename=os.path.join(directory, tmp+'.mat'))

            for r in runs:
                FilterPeaks(InputWorkspace=tmp, 
                            FilterVariable='RunNumber',
                            FilterValue=r,
                            Operator='=',
                            OutputWorkspace=opk.format(r))

        if mtd.doesExist('sa'):
            DeleteWorkspace('sa')

        if mtd.doesExist('flux'):
            DeleteWorkspace('flux')

        if mtd.doesExist('van'):
            DeleteWorkspace('van')

        if ref_dict is not None:
            ref_peak_dictionary = PeakDictionary(a, b, c, alpha, beta, gamma)
            ref_peak_dictionary.load(os.path.join(directory, ref_dict))
        else:
            ref_peak_dictionary = None

        peak_dictionary = PeakDictionary(a, b, c, alpha, beta, gamma)
        peak_dictionary.set_satellite_info(mod_vector_1, mod_vector_2, mod_vector_3, max_order)
        peak_dictionary.set_material_info(chemical_formula, z_parameter, sample_mass)
        peak_dictionary.set_scale_constant(scale_constant)

        for r in runs:

            if max_order > 0:

                ol = mtd[opk.format(r)].sample().getOrientedLattice()
                ol.setMaxOrder(max_order)

                ol.setModVec1(V3D(*mod_vector_1))
                ol.setModVec2(V3D(*mod_vector_2))
                ol.setModVec3(V3D(*mod_vector_3))

                UB = ol.getUB()

                mod_HKL = np.column_stack((mod_vector_1,mod_vector_2,mod_vector_3))
                mod_UB = np.dot(UB, mod_HKL)

                ol.setModUB(mod_UB)

                mod_1 = np.linalg.norm(mod_vector_1) > 0
                mod_2 = np.linalg.norm(mod_vector_2) > 0
                mod_3 = np.linalg.norm(mod_vector_3) > 0

                ind_1 = np.arange(-max_order*mod_1,max_order*mod_1+1).tolist()
                ind_2 = np.arange(-max_order*mod_2,max_order*mod_2+1).tolist()
                ind_3 = np.arange(-max_order*mod_3,max_order*mod_3+1).tolist()

                if cross_terms:
                    iter_mnp = list(itertools.product(ind_1,ind_2,ind_3))
                else:
                    iter_mnp = list(set(list(itertools.product(ind_1,[0],[0]))\
                                      + list(itertools.product([0],ind_2,[0]))\
                                      + list(itertools.product([0],[0],ind_3))))

                iter_mnp = [iter_mnp[s] for s in np.lexsort(np.array(iter_mnp).T, axis=0)]

                for pn in range(mtd[opk.format(r)].getNumberPeaks()):
                    pk = mtd[opk.format(r)].getPeak(pn)
                    hkl = pk.getHKL()
                    for m, n, p in iter_mnp:
                        d_hkl = m*np.array(mod_vector_1)\
                              + n*np.array(mod_vector_2)\
                              + p*np.array(mod_vector_3)
                        HKL = np.round(hkl-d_hkl,4)
                        mnp = [m,n,p]
                        H, K, L = HKL
                        h, k, l = int(H), int(K), int(L)
                        if reflection_condition == 'Primitive':
                            allowed = True
                        elif reflection_condition == 'C-face centred':
                            allowed = (h + k) % 2 == 0
                        elif reflection_condition == 'A-face centred':
                            allowed = (k + l) % 2 == 0
                        elif reflection_condition == 'B-face centred':
                            allowed = (h + l) % 2 == 0
                        elif reflection_condition == 'Body centred':
                            allowed = (h + k + l) % 2 == 0
                        elif reflection_condition == 'Rhombohedrally centred, obverse':
                            allowed = (-h + k + l) % 3 == 0
                        elif reflection_condition == 'Rhombohedrally centred, reverse':
                            allowed = (h - k + l) % 3 == 0
                        elif reflection_condition == 'Hexagonally centred, reverse':
                            allowed = (h - k) % 3 == 0
                        if np.isclose(np.linalg.norm(np.mod(HKL,1)), 0) and allowed:
                            HKL = HKL.astype(int).tolist()
                            pk.setIntMNP(V3D(*mnp))
                            pk.setIntHKL(V3D(*HKL))

            peak_dictionary.add_peaks(opk.format(r))

            if mtd.doesExist(opk.format(r)):
                DeleteWorkspace(opk.format(r))

        peak_dictionary.split_peaks(split_angle)
        peaks = peak_dictionary.to_be_integrated()

        ClearCache(AlgorithmCache=True, InstrumentCache=True, UsageServiceCache=True)

        keys = list(peaks.keys())
        split_keys = [split.tolist() for split in np.array_split(keys, n_proc)]

        filename = os.path.join(directory, tmp)

        args = [ref_peak_dictionary, ref_dict, filename,
                spectrum_file, counts_file, tube_calibration, detector_calibration,
                directory, facility, instrument, ipts, runs,
                split_angle, a, b, c, alpha, beta, gamma, reflection_condition,
                mod_vector_1, mod_vector_2, mod_vector_3, max_order, cross_terms,
                chemical_formula, z_parameter, sample_mass, experiment]

        join_args = [(split, outname+'_p{}'.format(i), *args) for i, split in enumerate(split_keys)]

        pool.starmap(merge.integration_loop, join_args)

        merger = PdfFileMerger()

        for i in range(n_proc):
            partfile = os.path.join(directory, outname+'_p{}'.format(i)+'.pdf')
            merger.append(partfile)

        merger.write(os.path.join(directory, outname+'.pdf'))       
        merger.close()

        if os.path.exists(os.path.join(directory, outname+'.pdf')):
            for i in range(n_proc):
                partfile = os.path.join(directory, outname+'_p{}'.format(i)+'.pdf')
                if os.path.exists(partfile):
                    os.remove(partfile)

        for i in range(n_proc):
            tmp_peak_dict = peak_dictionary.load_dictionary(os.path.join(directory, outname+'_p{}.pkl'.format(i)))

            if i == 0:
                peak_dict = copy.deepcopy(tmp_peak_dict)

            for key in list(tmp_peak_dict.keys()):
                peaks, tmp_peaks = peak_dict[key], tmp_peak_dict[key]

                new_peaks = []
                for peak, tmp_peak in zip(peaks, tmp_peaks):
                    if tmp_peak.get_merged_intensity() > 0:
                        new_peaks.append(tmp_peak)
                    else:
                        new_peaks.append(peak)
                peak_dict[key] = new_peaks

        peak_dictionary.peak_dict = peak_dict

        peak_dictionary._PeakDictionary__repopulate_workspaces()
        peak_dictionary.save(os.path.join(directory,outname+'.pkl'))
        peak_dictionary.save_hkl(os.path.join(directory,outname+'.hkl'))
        peak_dictionary.save_calibration(os.path.join(directory,outname+'_cal.nxs'))

        for i in range(n_proc):
            partfile = os.path.join(directory, outname+'_p{}'.format(i)+'.hkl')
            if os.path.exists(partfile):
                os.remove(partfile)
            partfile = os.path.join(directory, outname+'_p{}'.format(i)+'.pkl')
            if os.path.exists(partfile):
                os.remove(partfile)