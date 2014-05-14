'''
Created on Apr 30, 2014

@author: tpmaxwel
'''
from ColorMapManager import *
from ConfigurationFunctions import *
import vtk, traceback
MIN_LINE_LEN = 50
VTK_NOTATION_SIZE = 14

class ProcessMode:
    Default = 0
    Slicing = 1
    Thresholding = 2
    LowRes = 0
    HighRes = 1
    AnyRes = 2

class TextDisplayMgr:
    
    def __init__( self, renderer ):
        self.renderer = renderer
    
    def setTextPosition(self, textActor, pos, size=[400,30] ):
#        vpos = [ 2, 2 ] 
        vp = self.renderer.GetSize()
        vpos = [ pos[i]*vp[i] for i in [0,1] ]
        textActor.GetPositionCoordinate().SetValue( vpos[0], vpos[1] )      
        textActor.GetPosition2Coordinate().SetValue( vpos[0] + size[0], vpos[1] + size[1] )      
  
    def getTextActor( self, aid, text, pos, **args ):
        textActor = self.getProp( 'vtkTextActor', aid  )
        if textActor == None:
            textActor = self.createTextActor( aid, **args  )
            self.renderer.AddViewProp( textActor )
        self.setTextPosition( textActor, pos )
        text_lines = text.split('\n')
        linelen = len(text_lines[-1])
        if linelen < MIN_LINE_LEN: text += (' '*(MIN_LINE_LEN-linelen)) 
        text += '.' 
        textActor.SetInput( text )
        textActor.Modified()
        return textActor

    def getProp( self, ptype, pid = None ):
        try:
            props = self.renderer.GetViewProps()
            nitems = props.GetNumberOfItems()
            for iP in range(nitems):
                prop = props.GetItemAsObject(iP)
                if prop.IsA( ptype ):
                    if not pid or (prop.id == pid):
                        return prop
        except: 
            pass
        return None
  
    def createTextActor( self, aid, **args ):
        textActor = vtk.vtkTextActor()  
        textActor.SetTextScaleMode( vtk.vtkTextActor.TEXT_SCALE_MODE_PROP )  
#        textActor.SetMaximumLineHeight( 0.4 )       
        textprop = textActor.GetTextProperty()
        textprop.SetColor( *args.get( 'color', ( VTK_FOREGROUND_COLOR[0], VTK_FOREGROUND_COLOR[1], VTK_FOREGROUND_COLOR[2] ) ) )
        textprop.SetOpacity ( args.get( 'opacity', 1.0 ) )
        textprop.SetFontSize( args.get( 'size', 10 ) )
        if args.get( 'bold', False ): textprop.BoldOn()
        else: textprop.BoldOff()
        textprop.ItalicOff()
        textprop.ShadowOff()
        textprop.SetJustificationToLeft()
        textprop.SetVerticalJustificationToBottom()        
        textActor.GetPositionCoordinate().SetCoordinateSystemToDisplay()
        textActor.GetPosition2Coordinate().SetCoordinateSystemToDisplay() 
        textActor.VisibilityOff()
        textActor.id = aid
        return textActor 
    
class DV3DPlot():  
    
    NoModifier = 0
    ShiftModifier = 1
    CtrlModifier = 2
    AltModifier = 3
    
    LEFT_BUTTON = 0
    RIGHT_BUTTON = 1

    sliceAxes = [ 'x', 'y', 'z' ]       
 
    def __init__( self,  **args ):
        self.labelBuff = ""
        self.textDisplayMgr = None
        self.useGui = args.get( 'gui', True )
        self.renderWindow = args.get( 'renwin', self.createRenderWindow() )
        self.renderWindowInteractor = self.renderWindow.GetInteractor()
        self.navigationInteractorStyle = args.get( 'istyle', vtk.vtkInteractorStyleTrackballCamera() )  
        self.renderWindowInteractor.SetInteractorStyle( self.navigationInteractorStyle )
        self.cameraOrientation = {}
        self.maxStageHeight = 100.0
        self.observerTargets = set()
        self.enableClip = False
        self.xcenter = 100.0
        self.xwidth = 300.0
        self.ycenter = 0.0
        self.ywidth = 180.0
        self.widget = None
        self.process_mode = ProcessMode.Default
        
        self.configuring = False
        self.configurableFunctions = {}
        self.configurationInteractorStyle = vtk.vtkInteractorStyleUser()
        self.activated = False

        self.isAltMode = False
        self.createColormap = True
        self.InteractionState = None
        self.LastInteractionState = None
        self.colormapManagers= {}
        self.currentSliders = {} 
        self.addConfigurableSliderFunction( 'zScale', 'z', label='Vertical Scaling', sliderLabels='Vertical Scale', interactionHandler=self.processVerticalScalingCommand, range_bounds=[ 0.1, 10.0 ], initValue= 1.0  )

    def addConfigurableFunction(self, name, function_args, key, **args):
        self.configurableFunctions[name] = ConfigurableFunction( name, function_args, key, **args )

    def addConfigurableSliderFunction(self, name, key, **args):
        self.configurableFunctions[name] = ConfigurableSliderFunction( name, key, **args )

    def getConfigFunction( self, name ):
        return self.configurableFunctions.get(name,None)

    def removeConfigurableFunction(self, name ):        
        del self.configurableFunctions[name]

    def applyConfiguration(self, **args ):       
        for configFunct in self.configurableFunctions.values():
            configFunct.applyParameter( **args  )

    def updateSliderWidgets(self, value0, value1 ): 
        for index, value in enumerate( ( value0, value1 ) ):
            if value <> None:
                ( process_mode, interaction_state, swidget ) = self.currentSliders[index]
                srep = swidget.GetRepresentation( )   
                srep.SetValue( value )
            
    def createSliderWidget( self, index ): 
        sliderRep = vtk.vtkSliderRepresentation2D()
        loc = [ [0.01,0.48], [0.52, 0.99 ] ] 
            
        sliderRep.GetPoint1Coordinate().SetCoordinateSystemToNormalizedDisplay()
        sliderRep.GetPoint1Coordinate().SetValue( loc[index][0], 0.06, 0 )
        sliderRep.GetPoint2Coordinate().SetCoordinateSystemToNormalizedDisplay()
        sliderRep.GetPoint2Coordinate().SetValue( loc[index][1], 0.06, 0 )
        prop = sliderRep.GetSliderProperty()
        prop.SetColor( 1.0, 0.0, 0.0 )
        prop.SetOpacity( 0.5 )
        sprop = sliderRep.GetSelectedProperty()
        sprop.SetOpacity( 0.8 )           
        tprop = sliderRep.GetTubeProperty()
        tprop.SetColor( 0.5, 0.5, 0.5 )
        tprop.SetOpacity( 0.5 )
        cprop = sliderRep.GetCapProperty()
        cprop.SetColor( 0.0, 0.0, 1.0 )
        cprop.SetOpacity( 0.5 )
#        sliderRep.PlaceWidget(  bounds   )  
        sliderRep.SetSliderLength(0.05)
        sliderRep.SetSliderWidth(0.02)
        sliderRep.SetTubeWidth(0.01)
        sliderRep.SetEndCapLength(0.02)
        sliderRep.SetEndCapWidth(0.02)
        sliderRep.SetTitleHeight( 0.02 )    
        sliderWidget = vtk.vtkSliderWidget()
        sliderWidget.SetInteractor(self.renderWindowInteractor)
        sliderWidget.SetRepresentation( sliderRep )
        sliderWidget.SetAnimationModeToAnimate()
        sliderWidget.EnabledOn()
        sliderWidget.AddObserver("StartInteractionEvent", self.processStartInteractionEvent )
        sliderWidget.AddObserver("EndInteractionEvent", self.processEndInteractionEvent )
        sliderWidget.AddObserver("InteractionEvent", self.processInteractionEvent )
        sliderWidget.KeyPressActivationOff()
        return sliderWidget 
            
    def commandeerSlider(self, index, label, bounds, value ): 
        widget_item = self.currentSliders.get( index, None )
        if widget_item == None: 
            swidget = self.createSliderWidget(index) 
        else:
            ( process_mode, interaction_state, swidget ) = widget_item 
        srep = swidget.GetRepresentation( )      
        srep.SetTitleText( label )    
        srep.SetMinimumValue( bounds[ 0 ] )
        srep.SetMaximumValue( bounds[ 1 ]  )
        srep.SetValue( value )
        swidget.SetEnabled( 1 ) 
        self.currentSliders[index] = ( self.process_mode, self.InteractionState, swidget )
        
    def releaseSlider( self, index ):        
        ( process_mode, interaction_state, swidget ) = self.currentSliders.get( index, ( None, None, None ) )  
        if swidget: swidget.SetEnabled( 0 ) 
        
    def clearInteractions(self):
        if self.InteractionState <> None: 
            configFunct = self.configurableFunctions[ self.InteractionState ]
            configFunct.close()   
        self.process_mode = ProcessMode.Default
        self.config_mode = ConfigMode.Default
        self.InteractionState = None
        for ( process_mode, interaction_state, swidget ) in self.currentSliders.values():
            swidget.SetEnabled( 0 ) 

    def processInteractionEvent( self, obj=None, event=None ):
#        print " processInteractionEvent: ( %s %d )" % ( self.InteractionState, self.process_mode )
        if ( self.InteractionState <> None ): 
            srep = obj.GetRepresentation( ) 
            config_function = self.getConfigFunction( self.InteractionState )
            config_function.processInteractionEvent( [ "UpdateConfig", self.getSliderIndex(obj), srep.GetValue() ] )                         
#         else:
#             if self.process_mode == ProcessMode.Slicing:
#                 ( process_mode, interaction_state, swidget ) = self.currentSliders[1] 
#                 slice_pos = swidget.GetRepresentation( ).GetValue()
#                 self.pushSlice( slice_pos )         

    def processStartInteractionEvent( self, obj, event ): 
        slider_index = self.checkInteractionState( obj, event ) 
#        print " processStartInteractionEvent: ( %s %d )" % ( self.InteractionState, self.process_mode )
        if ( self.InteractionState <> None ): 
            config_function = self.getConfigFunction( self.InteractionState )
            config_function.processInteractionEvent( [ "StartConfig", slider_index ] )  
#         else:   
#             if self.process_mode == ProcessMode.Slicing:
#                 self.setRenderMode( ProcessMode.LowRes )
                
    def checkInteractionState( self, obj, event ):
        for item in self.currentSliders.items():
            ( process_mode, interaction_state, swidget ) = item[1]
            if ( id( swidget ) == id( obj ) ): 
                if self.InteractionState <> interaction_state:            
                    self.processEndInteractionEvent( obj, event )
                    if self.InteractionState <> None: self.endInteraction()
                    self.InteractionState = interaction_state
                    self.process_mode = process_mode
                    print "Change Interaction State: %s %d " % ( self.InteractionState, self.process_mode )
                return item[0]
        return None
            
    def getSliderIndex(self, obj ):
        for index in self.currentSliders:
            ( process_mode, interaction_state, swidget ) = self.currentSliders[index]
            if ( id( swidget ) == id( obj ) ): return index
        return None

    def processEndInteractionEvent( self, obj, event ):  
#        print " processEndInteractionEvent: ( %s %d )" % ( self.InteractionState, self.process_mode )
        if ( self.InteractionState <> None ): 
            config_function = self.getConfigFunction( self.InteractionState )
            config_function.processInteractionEvent( [ "EndConfig" ] )  

    def displayEventType(self, caller, event):
        print " --> Event: %s " % event 
        return 0
        
    def processTimerEvent(self, caller, event):
        id0 = caller.GetTimerEventId ()
        return 0
#         id1 = caller.GetTimerEventType ()
#         id2 = caller.GetTimerEventPlatformId ()
#        print "TimerEvent: %d %d %d " % (  id0, id1, id2 )
        
    def setInteractionState(self, caller, event):
        key = caller.GetKeyCode() 
        keysym = caller.GetKeySym()
        shift = caller.GetShiftKey()
#        print " setInteractionState -- Key Press: %c ( %d: %s ), event = %s " % ( key, ord(key), str(keysym), str( event ) )
        alt = ( keysym <> None) and keysym.startswith("Alt")
        if alt:
            self.isAltMode = True
        else: 
            self.processKeyEvent( key, caller, event )
        return 0

    def processKeyEvent( self, key, caller=None, event=None ):
        keysym = caller.GetKeySym()
        if self.onKeyEvent( [ key, keysym ] ):
            pass
        else:
            ( state, persisted ) =  self.getInteractionState( key )
    #            print " %s Set Interaction State: %s ( currently %s) " % ( str(self.__class__), state, self.InteractionState )
            if state <> None: 
                print " ------------------------------------------ setInteractionState, key=%s, state = %s    ------------------------------------------ " % (str(key), str(state)  )
                self.updateInteractionState( state  )                 
                self.isAltMode = False 
        return 0

    def onLeftButtonPress( self, caller, event ):
#        istyle = self.renderWindowInteractor.GetInteractorStyle()
#        print "(%s)-LBP: s = %s, nis = %s " % ( getClassName( self ), getClassName(istyle), getClassName(self.navigationInteractorStyle) )
        if not self.finalizeLeveling(): 
#            shift = caller.GetShiftKey()
            self.currentButton = self.LEFT_BUTTON
 #           self.clearInstructions()
            self.UpdateCamera()   
            x, y = caller.GetEventPosition()      
            self.startConfiguration( x, y, [ 'leveling', 'generic' ] )  
        return 0

    def onRightButtonPress( self, caller, event ):
        shift = caller.GetShiftKey()
        self.currentButton = self.RIGHT_BUTTON
 #       self.clearInstructions()
        self.UpdateCamera()
        x, y = caller.GetEventPosition()
        if self.InteractionState <> None:
            self.startConfiguration( x, y,  [ 'generic' ] )
        return 0

    def onLeftButtonRelease( self, caller, event ):
        self.currentButton = None 
    
    def onRightButtonRelease( self, caller, event ):
        self.currentButton = None 

    def startConfiguration( self, x, y, config_types ): 
        if (self.InteractionState <> None) and not self.configuring:
            configFunct = self.configurableFunctions[ self.InteractionState ]
            if configFunct.type in config_types:
                self.configuring = True
                configFunct.start( self.InteractionState, x, y )
                self.haltNavigationInteraction()
#                if (configFunct.type == 'leveling'): self.getLabelActor().VisibilityOn()

    def updateLevelingEvent( self, caller, event ):
        x, y = caller.GetEventPosition()
        wsize = caller.GetRenderWindow().GetSize()
        self.updateLeveling( x, y, wsize )
                
    def updateLeveling( self, x, y, wsize, **args ):  
        if self.configuring:
            configFunct = self.configurableFunctions[ self.InteractionState ]
            if configFunct.type == 'leveling':
                configData = configFunct.update( self.InteractionState, x, y, wsize )
                if configData <> None:
                    self.setParameter( configFunct.name, configData ) 
                    textDisplay = configFunct.getTextDisplay()
                    if textDisplay <> None:  self.updateTextDisplay( textDisplay )
                    self.render()

    def updateTextDisplay( self, text, render=False ):
        if text <> None:
            self.labelBuff = "%s" % str(text) 
        label_actor = self.getLabelActor()
        if label_actor: label_actor.VisibilityOn() 
        if render: self.render()     

    def getLabelActor(self):
        return self.textDisplayMgr.getTextActor( 'label', self.labelBuff, (.01, .90), size = VTK_NOTATION_SIZE, bold = True  ) if self.textDisplayMgr else None
    
    def UpdateCamera(self):
        pass
    
    def setParameter( self, name, value ):
        pass

    def haltNavigationInteraction(self):
        pass
#        print " ---------------------- haltNavigationInteraction -------------------------- "
        if self.renderWindowInteractor:
            self.renderWindowInteractor.SetInteractorStyle( self.configurationInteractorStyle )  
    
    def resetNavigation(self):
        pass
#         print " ---------------------- resetNavigation -------------------------- "
        if self.renderWindowInteractor:
            self.renderWindowInteractor.SetInteractorStyle( self.navigationInteractorStyle )
            self.enableVisualizationInteraction()

    def getInteractionState( self, key ):
        for configFunct in self.configurableFunctions.values():
            if configFunct.matches( key ): return ( configFunct.name, configFunct.persisted )
        return ( None, None )    

    def updateInteractionState( self, state ):    
        rcf = None
        if state == None: 
            self.finalizeLeveling()
            self.endInteraction()   
        else:            
            if self.InteractionState <> None: 
                configFunct = self.configurableFunctions[ self.InteractionState ]
                configFunct.close()   
            configFunct = self.configurableFunctions.get( state, None )
            if configFunct and ( configFunct.type <> 'generic' ): 
                rcf = configFunct
#                print " UpdateInteractionState, state = %s, cf = %s " % ( state, str(configFunct) )
            if not configFunct and self.acceptsGenericConfigs:
                configFunct = ConfigurableFunction( state, None, None )              
                self.configurableFunctions[ state ] = configFunct
            if configFunct:
                configFunct.open( state )
                self.InteractionState = state                   
                self.LastInteractionState = self.InteractionState
                self.disableVisualizationInteraction()               
                if (configFunct.type == 'slider'):
                    configFunct.processInteractionEvent( [ "InitConfig" ] )
                    tvals = configFunct.value.getValues()
                    for slider_index in range(2):
                        if slider_index < len(configFunct.sliderLabels):
                            self.commandeerSlider( slider_index, configFunct.sliderLabels[slider_index], configFunct.range_bounds, tvals[slider_index]  ) # config_funct.initial_value[slider_index] )
                        else:
                            self.releaseSlider( slider_index )
                self.render()

            elif state == 'colorbar':
                self.toggleColormapVisibility()                        
            elif state == 'reset':
                self.resetCamera()              
                if  len(self.persistedParameters):
                    pname = self.persistedParameters.pop()
                    configFunct = self.configurableFunctions[pname]
                    param_value = configFunct.reset() 
                    if param_value: self.persistParameterList( [ (configFunct.name, param_value), ], update=True, list=False )                                      
        return rcf

    def enableVisualizationInteraction(self): 
        pass

    def disableVisualizationInteraction(self):
        pass
    
    def printInteractionStyle(self, msg ):
        print "%s: InteractionStyle = %s " % ( msg,  self.renderWindow.GetInteractor().GetInteractorStyle().__class__.__name__ ) 
    
    def getLut( self, cmap_index=0  ):
        colormapManager = self.getColormapManager( index=cmap_index )
        return colormapManager.lut
        
    def updatingColormap( self, cmap_index, colormapManager ):
        pass

    def addObserver( self, target, event, observer ):
        self.observerTargets.add( target ) 
        target.AddObserver( event, observer ) 

    def createRenderer(self, **args ):
        background_color = args.get( 'background_color', VTK_BACKGROUND_COLOR )
        self.renderer.SetBackground(*background_color)   
        self.renderWindowInteractor.AddObserver( 'RightButtonPressEvent', self.onRightButtonPress )  
        self.textDisplayMgr = TextDisplayMgr( self.renderer )             
        self.pointPicker = vtk.vtkPointPicker()
        self.pointPicker.PickFromListOn()   
        try:        self.pointPicker.SetUseCells(True)  
        except:     print>>sys.stderr,  "Warning, vtkPointPicker patch not installed, picking will not work properly."
        self.pointPicker.InitializePickList()             
        self.renderWindowInteractor.SetPicker(self.pointPicker) 
        self.addObserver( self.renderer, 'ModifiedEvent', self.activateEvent )
        if self.enableClip:
            self.clipper = vtk.vtkBoxWidget()
            self.clipper.RotationEnabledOff()
            self.clipper.SetPlaceFactor( 1.0 ) 
            self.clipper.KeyPressActivationOff()
            self.clipper.SetInteractor( self.renderWindowInteractor )    
            self.clipper.SetHandleSize( 0.005 )
            self.clipper.SetEnabled( True )
            self.clipper.InsideOutOn()  
           
#        self.clipper.AddObserver( 'StartInteractionEvent', self.startClip )
#        self.clipper.AddObserver( 'EndInteractionEvent', self.endClip )
#        self.clipper.AddObserver( 'InteractionEvent', self.executeClip )
            self.clipOff() 

    def isConfigStyle( self, iren ):
        if not iren: return False
        return getClassName( iren.GetInteractorStyle() ) == getClassName( self.configurationInteractorStyle )
            
    def onKeyRelease(self, caller, event):
        return 0
        
    def onModified(self, caller, event):
#        print " --- Modified Event --- "
        return 0
    
    def onRender(self, caller, event):
        return 0
    
    def updateInteractor(self): 
        return 0    
    
    def activateEvent( self, caller, event ):
        if not self.activated:
#            self.addObserver( self.renderWindowInteractor, 'InteractorEvent', self.displayEventType )                   
            self.addObserver( self.renderWindowInteractor, 'CharEvent', self.setInteractionState )                   
            self.addObserver( self.renderWindowInteractor, 'TimerEvent', self.processTimerEvent )                   
            self.addObserver( self.renderWindowInteractor, 'MouseMoveEvent', self.updateLevelingEvent )
            self.addObserver( self.renderWindowInteractor, 'KeyReleaseEvent', self.onKeyRelease )
            self.addObserver( self.renderWindowInteractor, 'LeftButtonPressEvent', self.onLeftButtonPress )            
            self.addObserver( self.renderWindowInteractor, 'ModifiedEvent', self.onModified )
            self.addObserver( self.renderWindowInteractor, 'RenderEvent', self.onRender )                   
            self.addObserver( self.renderWindowInteractor, 'LeftButtonReleaseEvent', self.onLeftButtonRelease )
            self.addObserver( self.renderWindowInteractor, 'RightButtonReleaseEvent', self.onRightButtonRelease )
            self.addObserver( self.renderWindowInteractor, 'RightButtonPressEvent', self.onRightButtonPress )
            self.updateInteractor() 
            self.activated = True 

    def clearReferrents(self):
        self.removeObservers()
        self.renderer = None
        self.renderWindowInteractor = None

    def removeObservers( self ): 
        for target in self.observerTargets:
            target.RemoveAllObservers()
        self.observerTargets.clear()

    def createRenderWindow(self):
        self.renderer = vtk.vtkRenderer()
        renWin = vtk.vtkRenderWindow()
        renWin.AddRenderer( self.renderer )
        self.renderWindowInteractor = vtk.vtkRenderWindowInteractor()
        self.renderWindowInteractor.SetRenderWindow(renWin)            
        return renWin
    
    def closeConfigDialog(self):
        pass
    
    def enableRender(self, **args ):
        return True

    def render( self, **args ):
        if self.enableRender( **args ):
            self.renderWindow.Render()

    def processEvent(self, eventArgs ):
        if eventArgs[0] == "KeyEvent":
            self.onKeyEvent( eventArgs[1:])
        if eventArgs[0] == "ResizeEvent":
            self.onResizeEvent()           
            
    def onKeyEvent(self, eventArgs ):
        pass

    def getLUT( self, cmap_index=0  ):
        colormapManager = self.getColormapManager( index=cmap_index )
        return colormapManager.lut

    def toggleColormapVisibility(self):
        for colormapManager in self.colormapManagers.values():
            colormapManager.toggleColormapVisibility()
        self.render()
    
    def getColormapManager( self, **args ):
        cmap_index = args.get('index',0)
        name = args.get('name',None)
        invert = args.get('invert',None)
        smooth = args.get('smooth',None)
        cmap_mgr = self.colormapManagers.get( cmap_index, None )
        if cmap_mgr == None:
            lut = vtk.vtkLookupTable()
            cmap_mgr = ColorMapManager( lut ) 
            self.colormapManagers[cmap_index] = cmap_mgr
        if (invert <> None): cmap_mgr.invertColormap = invert
        if (smooth <> None): cmap_mgr.smoothColormap = smooth
        if name:   cmap_mgr.load_lut( name )
        return cmap_mgr
        
    def setColormap( self, data, **args ):
        colormapName = str(data[0])
        invertColormap = getBool( data[1] ) 
        enableStereo = getBool( data[2] )
        show_colorBar = getBool( data[3] ) if ( len( data ) > 3 ) else 0 
        cmap_index = args.get( 'index', 0 )
        metadata = self.getMetadata()
        var_name = metadata.get( 'var_name', '')
        var_units = metadata.get( 'var_units', '')
        self.updateStereo( enableStereo )
        colormapManager = self.getColormapManager( name=colormapName, invert=invertColormap, index=cmap_index, units=var_units )
        if( colormapManager.colorBarActor == None ): 
            cm_title = str.replace( "%s (%s)" % ( var_name, var_units ), " ", "\n" )
            cmap_pos = [ 0.9, 0.2 ] if (cmap_index==0) else [ 0.02, 0.2 ]
            self.renderer.AddActor( colormapManager.createActor( pos=cmap_pos, title=cm_title ) )
        colormapManager.setColorbarVisibility( show_colorBar )
        self.render() 
        return True
        return False 
    
    def getUnits(self, var_index ):
        return ""
    
    def getMetadata(self):
        return self.metadata
    

    def updateStereo( self, enableStereo ):   
        if enableStereo:
            self.renderWindow.StereoRenderOn()
            self.stereoEnabled = 1
        else:
            self.renderWindow.StereoRenderOff()
            self.stereoEnabled = 0

            
    def getColormap(self, cmap_index = 0 ):
        colormapManager = self.getColormapManager( index=cmap_index )
        return [ colormapManager.colormapName, colormapManager.invertColormap, self.stereoEnabled ]

    def start(self):
        self.renderWindowInteractor.Initialize()
        self.renderWindow.Render()
        self.renderWindowInteractor.Start()
         
    def invalidate(self):
        self.isValid = False

#     def startEventLoop(self):
#         self.renderWindowInteractor.Start()

    def recordCamera( self ):
        c = self.renderer.GetActiveCamera()
        self.cameraOrientation[ self.topo ] = ( c.GetPosition(), c.GetFocalPoint(), c.GetViewUp() )

    def resetCamera( self, pts = None ):
        cdata = self.cameraOrientation.get( self.topo, None )
        if cdata:
            self.renderer.GetActiveCamera().SetPosition( *cdata[0] )
            self.renderer.GetActiveCamera().SetFocalPoint( *cdata[1] )
            self.renderer.GetActiveCamera().SetViewUp( *cdata[2] )       
        elif pts:
            self.renderer.ResetCamera( pts.GetBounds() )
        else:
            self.renderer.ResetCamera( self.getBounds() )
            
    def initCamera(self):
        self.renderer.GetActiveCamera().SetPosition( self.xcenter, self.ycenter, 400.0 )
        self.renderer.GetActiveCamera().SetFocalPoint( self.xcenter, self.ycenter, 0.0 )
        self.renderer.GetActiveCamera().SetViewUp( 0, 1, 0 )  
        self.renderer.ResetCameraClippingRange()     
            
    def getCamera(self):
        return self.renderer.GetActiveCamera()
    
    def setFocalPoint( self, fp ):
        self.renderer.GetActiveCamera().SetFocalPoint( *fp )
        
    def printCameraPos( self, label = "" ):
        cam = self.getCamera()
        cpos = cam.GetPosition()
        cfol = cam.GetFocalPoint()
        cup = cam.GetViewUp()
        camera_pos = (cpos,cfol,cup)
        print "%s: Camera => %s " % ( label, str(camera_pos) )

    def update(self):
        pass

    def getColormapSpec(self, cmap_index=0): 
        colormapManager = self.getColormapManager( index=cmap_index )
        spec = []
        spec.append( colormapManager.colormapName )
        spec.append( str( colormapManager.invertColormap ) )
        value_range = colormapManager.lut.GetTableRange() 
        spec.append( str( value_range[0] ) )
        spec.append( str( value_range[1] ) ) 
#        print " %s -- getColormapSpec: %s " % ( self.getName(), str( spec ) )
        return ','.join( spec )

    def onKeyPress( self, caller, event ):
        key = caller.GetKeyCode() 
        keysym = caller.GetKeySym()
        print " -- Key Press: %s ( %s ), event = %s " % ( key, str(keysym), str( event ) )
        if keysym == None: return
        alt = ( keysym.lower().find('alt') == 0 )
        ctrl = caller.GetControlKey() 
        shift = caller.GetShiftKey() 

    def finalizeLeveling( self, cmap_index=0 ):
        if self.configuring: 
            self.finalizeConfigurationObserver( self.InteractionState )            
            self.resetNavigation()
            self.configuring = False
            self.InteractionState = None
            return True
        return False
#            self.updateSliceOutput()

    def finalizeConfigurationObserver( self, parameter_name, **args ):
        self.finalizeParameter( parameter_name, **args )
        self.endConfiguration()    
#        for parameter_name in self.getModuleParameters(): self.finalizeParameter( parameter_name, *args ) 
        self.endInteraction( **args ) 

    def finalizeParameter(self, parameter_name, **args ):
        pass
    
    def endInteraction( self, **args ):  
        self.resetNavigation() 
        self.configuring = False
        self.InteractionState = None
        self.enableVisualizationInteraction()

    def endConfiguration( self ):
        pass
           
    def initializeConfiguration( self, **args ):
        for configFunct in self.configurableFunctions.values():
            configFunct.init( **args )